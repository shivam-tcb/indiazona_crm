frappe.ui.form.on('CRM Lead', {
    refresh: function (frm) {
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
    }
});
