frappe.listview_settings["Attendance Reconciliation Log"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Reconcile Backdated"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Reconcile Late Checkins"),
				fields: [
					{
						fieldname: "from_date",
						fieldtype: "Date",
						label: __("From Date"),
						reqd: 1,
						default: frappe.datetime.add_days(frappe.datetime.nowdate(), -7),
					},
					{
						fieldname: "to_date",
						fieldtype: "Date",
						label: __("To Date"),
						reqd: 1,
						default: frappe.datetime.add_days(frappe.datetime.nowdate(), -1),
					},
				],
				primary_action_label: __("Run"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "hrms_enhanced.attendance.reconciliation.manual_backdate_reconcile",
						args: values,
						freeze: true,
						freeze_message: __("Scanning for Absent records with late checkins..."),
						callback(r) {
							if (r.message) {
								frappe.msgprint(
									__("Found {0} Absent records, queued {1} for reconciliation.", [
										r.message.total_absent,
										r.message.queued,
									])
								);
								listview.refresh();
							}
						},
					});
				},
			});
			d.show();
		});
	},

	get_indicator(doc) {
		const status = doc.new_status;
		if (status === "Present") return [__("Present"), "green", "new_status,=,Present"];
		if (status === "Half Day") return [__("Half Day"), "orange", "new_status,=,Half Day"];
		if (status === "Error") return [__("Error"), "red", "new_status,=,Error"];
		if (status === "Skipped") return [__("Skipped"), "grey", "new_status,=,Skipped"];
		return [__(status), "blue", `new_status,=,${status}`];
	},
};
