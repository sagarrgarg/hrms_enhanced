app_name = "hrms_enhanced"
app_title = "Hrms Enhanced"
app_publisher = "KGOPL"
app_description = "Attendance reconciliation for late biometric syncs"
app_email = "sagar1ratan1garg1@gmail.com"
app_license = "mit"

required_apps = ["hrms"]

doctype_list_js = {
	"Attendance": "public/js/attendance_list.js"
}

doc_events = {
	"Employee Checkin": {
		"after_insert": "hrms_enhanced.attendance.reconciliation.on_checkin_insert"
	}
}

scheduler_events = {
	"cron": {
		"30 23 * * *": [
			"hrms_enhanced.attendance.reconciliation.daily_sweep"
		]
	}
}
