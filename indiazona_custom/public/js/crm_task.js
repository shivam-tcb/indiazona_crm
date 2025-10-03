frappe.ui.form.on('CRM Task', {
    refresh: function(frm) {
        if (frm.doc.status === 'Call Back Scheduled' && !frm.doc.custom_callback_datetime) {
            frm.add_custom_button(__('📅 Schedule Callback'), function() {
                show_callback_dialog(frm);
            }).addClass('btn-primary');
        }
    },
    
    status: function(frm) {
        // Open popup immediately when status changes to "Call Back Scheduled"
        if (frm.doc.status === 'Call Back Scheduled' && !frm.doc.custom_callback_datetime) {
            // Prevent save until callback is scheduled
            setTimeout(function() {
                show_callback_dialog_before_save(frm);
            }, 200);
        }
    }
});

function show_callback_dialog_before_save(frm) {
    let d = new frappe.ui.Dialog({
        title: '📞 Schedule Callback',
        fields: [
            {
                label: 'Callback Date',
                fieldname: 'callback_date',
                fieldtype: 'Date',
                reqd: 1,
                default: frappe.datetime.add_days(frappe.datetime.nowdate(), 1)
            },
            {
                label: 'Callback Time',
                fieldname: 'callback_time',
                fieldtype: 'Time',
                reqd: 1,
                default: '10:00:00'
            },
            {
                fieldtype: 'Column Break'
            },
            {
                label: 'Notes',
                fieldname: 'callback_notes',
                fieldtype: 'Small Text',
                description: 'Any specific notes for the callback'
            }
        ],
        size: 'small',
        primary_action_label: 'Save & Schedule',
        primary_action(values) {
            let callback_datetime = values.callback_date + ' ' + values.callback_time;
            
            // First save the task
            frappe.show_alert({
                message: __('Saving task...'),
                indicator: 'blue'
            });
            
            frm.save().then(() => {
                // Then create callback
                frappe.call({
                    method: 'indiazona_custom.utils.auto_task.create_callback_task',
                    args: {
                        task_name: frm.doc.name,
                        callback_datetime: callback_datetime,
                        notes: values.callback_notes
                    },
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('✅ Callback scheduled!'),
                                indicator: 'green'
                            }, 5);
                            
                            if (frm.doc.custom_lead_name) {
                                setTimeout(function() {
                                    frappe.set_route('Form', 'CRM Lead', frm.doc.custom_lead_name);
                                }, 1500);
                            }
                        }
                    }
                });
            });
            
            d.hide();
        },
        secondary_action_label: 'Cancel',
        secondary_action() {
            // Reset status if user cancels
            frm.set_value('status', frm.doc.__last_sync_on ? 
                frappe.model.get_value(frm.doctype, frm.docname, 'status') : 'Todo');
            d.hide();
        }
    });
    
    d.show();
}
