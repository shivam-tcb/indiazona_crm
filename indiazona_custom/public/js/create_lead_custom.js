frappe.ui.form.on('CRM Lead', {
    refresh: function (frm) {
        // Your existing permission access call
        frappe.call({
            method: 'indiazona_custom.utils.permission_acess.update_status_log_owner_on_refresh',
            args: {
                doc_name: frm.doc.name
            },
            callback: function (r) {
                if (r.message && r.message.updated) {
                    frm.reload_doc();
                }
            }
        });

        // NEW: Add retry task check button
        frm.add_custom_button(__('Check Retry Tasks'), function() {
            frappe.show_alert({
                message: __('Checking for pending retry tasks...'),
                indicator: 'blue'
            });
            
            frappe.call({
                method: 'indiazona_custom.utils.auto_task.check_all_pending_retry_tasks',
                callback: function(r) {
                    frappe.show_alert({
                        message: __('Retry check completed!'),
                        indicator: 'green'
                    });
                    
                    // Reload page after 1 second to show new tasks
                    setTimeout(function() {
                        frm.reload_doc();
                    }, 1000);
                }
            });
        }, __('Actions'));
    }
});
