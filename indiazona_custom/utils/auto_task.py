import frappe
from frappe import _
from frappe.utils import nowdate, add_days, now_datetime, add_to_date

def create_task_for_lead(doc, method=None):
    """
    Create a task when a lead is created
    """
    try:
        # Create the initial task document
        task = frappe.get_doc({
            "doctype": "CRM Task",
            "title": "Make First Contact",
            "assigned_to": doc.lead_owner,
            "status": "Todo",
            "priority": "Medium",
            "description": f"Task auto-created for lead {doc.name}",
            "reference_doctype": "CRM Lead",
            "reference_docname": doc.name,
            "start_date": nowdate(),
            "due_date": add_days(nowdate(), 2),  # Due in 2 days
            "custom_attempt_number": 1,
            "custom_max_attempts": 10,
            "custom_retry_interval_days": 2,
            "custom_lead_name": doc.name
        })
        
        task.insert(ignore_permissions=True)
        
        # Assign task to lead owner if available
        if doc.get("lead_owner"):
            assignment = frappe.get_doc({
                "doctype": "ToDo",
                "allocated_to": doc.lead_owner,
                "reference_type": "CRM Task",
                "reference_name": task.name,
                "description": f"Task assigned: {task.title}",
                "priority": "Medium",
                "status": "Open"
            })
            assignment.insert(ignore_permissions=True)
            
            frappe.msgprint(
                _("Task {0} created and assigned to {1}").format(
                    task.name, doc.lead_owner
                ),
                alert=True
            )
        else:
            frappe.msgprint(
                _("Task {0} created successfully").format(task.name),
                alert=True
            )
            
    except Exception as e:
        frappe.log_error(
            message=f"Failed to create task for lead {doc.name}: {str(e)}",
            title="Lead Task Creation Error"
        )
        frappe.throw(_("Failed to create task for lead"))


def check_all_pending_retry_tasks():
    """
    Daily scheduled job to check all tasks needing retry
    """
    try:
        # Get tasks WITHOUT attempt number filter - let create_retry_task handle it
        tasks = frappe.get_all("CRM Task",
            filters={
                "status": "Call Not Connected",
                "due_date": ["<=", nowdate()],
                "custom_retry_created": 0
            },
            fields=["name", "custom_lead_name", "custom_attempt_number", "assigned_to", "custom_max_attempts"]
        )
        
        frappe.log_error(
            message=f"Found {len(tasks)} tasks to process",
            title="Daily Retry Check Started"
        )
        
        # Process all tasks - let create_retry_task decide what to do
        for task_data in tasks:
            try:
                attempt_num = int(task_data.custom_attempt_number) if task_data.custom_attempt_number else 1
                max_attempts = int(task_data.custom_max_attempts) if task_data.get("custom_max_attempts") else 10
                
                create_retry_task(
                    task_data.custom_lead_name,
                    task_data.name,
                    attempt_num,
                    task_data.assigned_to,
                    max_attempts
                )
            except Exception as e:
                frappe.log_error(
                    message=f"Error processing task {task_data.name}: {str(e)}",
                    title="Retry Task Processing Error"
                )
                continue
                
    except Exception as e:
        frappe.log_error(
            message=f"Error in daily retry check: {str(e)}",
            title="Daily Retry Check Error"
        )

def create_retry_task(lead_name, previous_task_name, attempt_number, assigned_to, max_attempts=10):
    """
    Create a retry task for a lead
    """
    try:

        attempt_number = int(attempt_number) if isinstance(attempt_number, str) else attempt_number
        max_attempts = int(max_attempts) if isinstance(max_attempts, str) else max_attempts


        # Get the previous task to verify status
        previous_task = frappe.get_doc("CRM Task", previous_task_name)
        

        if previous_task.get("custom_retry_created"):
            frappe.log_error(
                message=f"Task {previous_task_name} already processed, skipping",
                title="Task Already Processed"
            )
            return
        
        # Double check status is still "Call Not Connected"
        if previous_task.status != "Call Not Connected":
            frappe.log_error(
                message=f"Task {previous_task_name} status changed to '{previous_task.status}', skipping retry",
                title="Status Changed - No Retry"
            )
            return
        
        
        

        # Check if we've reached max attempts
        if attempt_number >= max_attempts:
            # Mark as processed first
            previous_task.custom_retry_created = 1
            previous_task.save(ignore_permissions=True)


            # Update lead status to Inactive/Dropped
            lead_doc = frappe.get_doc("CRM Lead", lead_name)
            lead_doc.status = "Inactive / Dropped"
            lead_doc.add_comment(
                "Comment",
                f"Lead status automatically changed to 'Inactive / Dropped' after {max_attempts} unsuccessful contact attempts"
            )
            lead_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.log_error(
                message=f"Lead {lead_name} moved to Inactive/Dropped after {max_attempts} attempts",
                title="Max Retry Attempts Reached"
            )
            return
        
        # Create new retry task
        new_attempt = attempt_number + 1
        retry_task = frappe.get_doc({
            "doctype": "CRM Task",
            "title": f"Retry Call - Attempt {new_attempt}",
            "assigned_to": assigned_to,
            "status": "Todo",
            "priority": "Medium",
            "description": f"Retry task auto-created for lead {lead_name} - Attempt {new_attempt}/{max_attempts}",
            "reference_doctype": "CRM Lead",
            "reference_docname": lead_name,
            "start_date": nowdate(),
            "due_date": add_days(nowdate(), 2),  # Due in 2 days
            "custom_attempt_number":str(new_attempt),
            "custom_max_attempts": str(max_attempts),
            "custom_retry_interval_days": 2,
            "custom_lead_name": lead_name,
            "custom_previous_task": previous_task_name,
            "custom_retry_created": 0  # Not yet processed
        })
        
        retry_task.insert(ignore_permissions=True)
        
        previous_task.custom_retry_created = 1
        previous_task.save(ignore_permissions=True)

        # Create assignment
        if assigned_to:
            assignment = frappe.get_doc({
                "doctype": "ToDo",
                "allocated_to": assigned_to,
                "reference_type": "CRM Task",
                "reference_name": retry_task.name,
                "description": f"Retry task assigned: {retry_task.title}",
                "priority": "Medium",
                "status": "Open"
            })
            assignment.insert(ignore_permissions=True)
        
        frappe.db.commit()
        
        frappe.log_error(
            message=f"Retry task {retry_task.name} created for lead {lead_name} - Attempt {new_attempt}/{max_attempts}",
            title="Retry Task Created Successfully"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error creating retry task for lead {lead_name}: {str(e)}",
            title="Retry Task Creation Error"
        )
        raise
