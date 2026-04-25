import frappe
from frappe.utils import getdate, nowdate, add_days, now_datetime, get_datetime


def on_checkin_insert(doc, method):
	checkin_date = get_datetime(doc.time).date()
	if checkin_date == getdate(nowdate()):
		return

	employee = doc.employee
	attendance_date = str(checkin_date)

	absent_attendance = frappe.db.exists(
		"Attendance",
		{
			"employee": employee,
			"attendance_date": attendance_date,
			"status": "Absent",
			"docstatus": 1,
		},
	)
	if not absent_attendance:
		return

	frappe.enqueue(
		"hrms_enhanced.attendance.reconciliation.reconcile_attendance",
		queue="short",
		employee=employee,
		attendance_date=attendance_date,
		triggered_by_checkin=doc.name,
		checkin_time=str(doc.time),
		deduplicate=True,
		job_id=f"reconcile_{employee}_{attendance_date}",
	)


def reconcile_attendance(employee, attendance_date, triggered_by_checkin=None, checkin_time=None):
	lock_key = f"attendance_reconcile:{employee}:{attendance_date}"
	lock = frappe.cache.lock(lock_key, timeout=30)

	if not lock.acquire(blocking=False):
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="Absent",
			new_status="Skipped",
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes="Could not acquire lock — another reconciliation in progress",
		)
		return

	try:
		_do_reconcile(employee, attendance_date, triggered_by_checkin, checkin_time)
	except Exception:
		frappe.log_error(
			title=f"Attendance Reconciliation Failed: {employee} {attendance_date}",
		)
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="Absent",
			new_status="Error",
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes=frappe.get_traceback(with_context=True)[:2000],
		)
	finally:
		try:
			lock.release()
		except Exception:
			pass


def _do_reconcile(employee, attendance_date, triggered_by_checkin, checkin_time):
	attendance_date = str(getdate(attendance_date))

	# skip if approved leave attendance exists
	leave_attendance = frappe.db.exists(
		"Attendance",
		{
			"employee": employee,
			"attendance_date": attendance_date,
			"status": "On Leave",
			"docstatus": 1,
		},
	)
	if leave_attendance:
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="On Leave",
			new_status="Skipped",
			attendance_record=leave_attendance,
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes="Leave attendance exists — skipping",
		)
		return

	# skip if submitted Salary Slip covers this date
	salary_slip = frappe.db.exists(
		"Salary Slip",
		{
			"employee": employee,
			"start_date": ("<=", attendance_date),
			"end_date": (">=", attendance_date),
			"docstatus": 1,
		},
	)
	if salary_slip:
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="Absent",
			new_status="Skipped",
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes=f"Submitted Salary Slip {salary_slip} covers this date — skipping",
		)
		return

	# find the Absent attendance record
	absent_name = frappe.db.exists(
		"Attendance",
		{
			"employee": employee,
			"attendance_date": attendance_date,
			"status": "Absent",
			"docstatus": 1,
		},
	)
	if not absent_name:
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="",
			new_status="Skipped",
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes="No Absent attendance found — may have been reconciled already",
		)
		return

	absent_doc = frappe.get_doc("Attendance", absent_name)
	shift_name = absent_doc.shift

	# get all checkins for this employee/date that are not skipped
	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"time": ("between", [f"{attendance_date} 00:00:00", f"{attendance_date} 23:59:59"]),
			"skip_auto_attendance": 0,
		},
		fields=[
			"name", "employee", "log_type", "time", "shift",
			"shift_start", "shift_end", "shift_actual_start", "shift_actual_end",
			"device_id",
		],
		order_by="time asc",
	)

	if not checkins:
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="Absent",
			new_status="Skipped",
			attendance_record=absent_name,
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes="No valid checkins found for this date",
		)
		return

	# if shift is known, filter checkins to that shift; also try checkins with matching shift
	if shift_name:
		shift_checkins = [c for c in checkins if c.shift == shift_name]
		if shift_checkins:
			checkins = shift_checkins

	# compute attendance using ShiftType logic
	shift_to_use = shift_name or (checkins[0].shift if checkins[0].shift else None)

	if shift_to_use:
		try:
			shift_doc = frappe.get_cached_doc("Shift Type", shift_to_use)
			attendance_status, working_hours, late_entry, early_exit, in_time, out_time = (
				shift_doc.get_attendance(checkins)
			)
		except Exception:
			# fallback: if shift calculation fails, mark Present with basic working hours
			from hrms.hr.doctype.employee_checkin.employee_checkin import calculate_working_hours

			working_hours, in_time, out_time = calculate_working_hours(
				checkins,
				"Alternating entries as IN and OUT during the same shift",
				"First Check-in and Last Check-out",
			)
			attendance_status = "Present"
			late_entry = False
			early_exit = False
	else:
		from hrms.hr.doctype.employee_checkin.employee_checkin import calculate_working_hours

		working_hours, in_time, out_time = calculate_working_hours(
			checkins,
			"Alternating entries as IN and OUT during the same shift",
			"First Check-in and Last Check-out",
		)
		attendance_status = "Present"
		late_entry = False
		early_exit = False

	if attendance_status == "Absent":
		_log_reconciliation(
			employee=employee,
			attendance_date=attendance_date,
			previous_status="Absent",
			new_status="Absent (recomputed)",
			attendance_record=absent_name,
			triggered_by_checkin=triggered_by_checkin,
			checkin_time=checkin_time,
			notes="Recomputed status is still Absent — no change needed",
		)
		return

	# in-place overwrite using db_set pattern from Attendance Request
	update_values = {
		"status": attendance_status,
		"working_hours": working_hours,
		"late_entry": late_entry,
		"early_exit": early_exit,
		"in_time": in_time,
		"out_time": out_time,
	}
	if shift_to_use:
		update_values["shift"] = shift_to_use

	absent_doc.db_set(update_values)

	absent_doc.add_comment(
		comment_type="Info",
		text=(
			f"Attendance reconciled from Absent to {attendance_status} "
			f"by hrms_enhanced (triggered by late checkin sync). "
			f"Working hours: {working_hours}, Late: {late_entry}, Early exit: {early_exit}"
		),
	)

	# link checkins to this attendance record
	log_names = [c.name for c in checkins]
	from hrms.hr.doctype.employee_checkin.employee_checkin import update_attendance_in_checkins

	update_attendance_in_checkins(log_names, absent_name)

	_log_reconciliation(
		employee=employee,
		attendance_date=attendance_date,
		previous_status="Absent",
		new_status=attendance_status,
		attendance_record=absent_name,
		triggered_by_checkin=triggered_by_checkin,
		checkin_time=checkin_time,
		notes=f"Working hours: {working_hours}, Shift: {shift_to_use}",
	)

	frappe.db.commit()


def daily_sweep():
	today = getdate(nowdate())

	for days_ago in range(1, 4):
		date = str(add_days(today, -days_ago))

		absent_records = frappe.get_all(
			"Attendance",
			filters={
				"attendance_date": date,
				"status": "Absent",
				"docstatus": 1,
			},
			fields=["name", "employee"],
		)

		for record in absent_records:
			has_checkins = frappe.db.exists(
				"Employee Checkin",
				{
					"employee": record.employee,
					"time": ("between", [f"{date} 00:00:00", f"{date} 23:59:59"]),
					"skip_auto_attendance": 0,
				},
			)

			if has_checkins:
				frappe.enqueue(
					"hrms_enhanced.attendance.reconciliation.reconcile_attendance",
					queue="long",
					employee=record.employee,
					attendance_date=date,
					triggered_by_checkin="daily_sweep",
					checkin_time=str(now_datetime()),
					deduplicate=True,
					job_id=f"reconcile_{record.employee}_{date}",
				)


@frappe.whitelist()
def manual_backdate_reconcile(from_date, to_date):
	frappe.only_for(["System Manager", "HR Manager"])

	from_date = getdate(from_date)
	to_date = getdate(to_date)
	today = getdate(nowdate())

	if to_date >= today:
		to_date = add_days(today, -1)
	if from_date > to_date:
		frappe.throw("From Date must be before To Date")

	absent_records = frappe.get_all(
		"Attendance",
		filters={
			"attendance_date": ("between", [str(from_date), str(to_date)]),
			"status": "Absent",
			"docstatus": 1,
		},
		fields=["name", "employee", "attendance_date"],
	)

	queued = 0
	for record in absent_records:
		date = str(record.attendance_date)
		has_checkins = frappe.db.exists(
			"Employee Checkin",
			{
				"employee": record.employee,
				"time": ("between", [f"{date} 00:00:00", f"{date} 23:59:59"]),
				"skip_auto_attendance": 0,
			},
		)
		if has_checkins:
			frappe.enqueue(
				"hrms_enhanced.attendance.reconciliation.reconcile_attendance",
				queue="long",
				employee=record.employee,
				attendance_date=date,
				triggered_by_checkin="manual_backdate",
				checkin_time=str(now_datetime()),
				deduplicate=True,
				job_id=f"reconcile_{record.employee}_{date}",
			)
			queued += 1

	return {"total_absent": len(absent_records), "queued": queued}


def _log_reconciliation(
	employee,
	attendance_date,
	previous_status,
	new_status,
	attendance_record=None,
	triggered_by_checkin=None,
	checkin_time=None,
	notes=None,
):
	try:
		frappe.get_doc(
			{
				"doctype": "Attendance Reconciliation Log",
				"employee": employee,
				"attendance_date": attendance_date,
				"previous_status": previous_status,
				"new_status": new_status,
				"attendance_record": attendance_record,
				"triggered_by_checkin": triggered_by_checkin,
				"checkin_time": checkin_time,
				"reconciled_at": now_datetime(),
				"notes": notes,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Failed to create Attendance Reconciliation Log")
