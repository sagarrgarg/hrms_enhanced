frappe.listview_settings["Attendance"] = Object.assign(
	frappe.listview_settings["Attendance"] || {},
	{
		onload(listview) {
			if (
				frappe.user.has_role("System Manager") ||
				frappe.user.has_role("HR Manager")
			) {
				listview.page.add_inner_button(
					__("Reconcile Late Checkins"),
					() => {
						const d = new frappe.ui.Dialog({
							title: __("Reconcile Late Checkins"),
							fields: [
								{
									fieldname: "from_date",
									fieldtype: "Date",
									label: __("From Date"),
									reqd: 1,
									default: frappe.datetime.add_days(
										frappe.datetime.nowdate(),
										-7
									),
								},
								{
									fieldname: "to_date",
									fieldtype: "Date",
									label: __("To Date"),
									reqd: 1,
									default: frappe.datetime.add_days(
										frappe.datetime.nowdate(),
										-1
									),
								},
							],
							primary_action_label: __("Run"),
							primary_action(values) {
								d.hide();
								frappe.call({
									method: "hrms_enhanced.attendance.reconciliation.manual_backdate_reconcile",
									args: values,
									freeze: true,
									freeze_message: __(
										"Scanning for Absent records with late checkins..."
									),
									callback(r) {
										if (r.message) {
											frappe.msgprint(
												__(
													"Found {0} Absent records, queued {1} for reconciliation.",
													[
														r.message.total_absent,
														r.message.queued,
													]
												)
											);
											listview.refresh();
										}
									},
								});
							},
						});
						d.show();
					},
					__("Actions")
				);
			}
		},
	}
);
