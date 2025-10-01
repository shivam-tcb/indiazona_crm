import frappe

@frappe.whitelist()
def update_status_log_owner_on_refresh(doc_name):
    """Update status log owner only once"""
    if not doc_name:
        return False
        
    try:
        doc = frappe.get_doc("CRM Lead", doc_name)
        
        assigned_user = doc.lead_owner if hasattr(doc, 'lead_owner') else None
        
        if not assigned_user:
            return False
        
        # Check if already updated (assume all rows have same log_owner when updated)
        already_updated = True
        for row in doc.status_change_log:
            if row.log_owner != assigned_user:
                already_updated = False
                break
        
        if already_updated:
            return {"message": "Already updated", "updated": False}
            
        # Update all rows in status_change_log child table
        for row in doc.status_change_log:
            row.log_owner = assigned_user
        
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {"message": "Updated successfully", "updated": True}
        
    except Exception as e:
        frappe.log_error(f"Error updating status log owner: {str(e)}")
        return False
