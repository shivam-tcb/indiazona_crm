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
            "due_date": add_days(nowdate(), 0),
            "custom_attempt_number": 1,
            "custom_max_attempts": 10,
            "custom_retry_interval_days": 2,
            "custom_lead_name": doc.name
        })
        
        task.insert(ignore_permissions=True)
        
        # Schedule the first retry check after 2 days
        schedule_retry_check(doc.name, task.name, 1)
        
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

def schedule_retry_check(lead_name, task_name, attempt_number):
    """
    Schedule a background job to check and create retry tasks after 2 days
    """
    # Calculate when to run the check (2 days from now)
    run_time = add_to_date(now_datetime(), minutes=2)
    
    # Enqueue the retry check job
    frappe.enqueue(
        'indiazona_custom.utils.auto_task.check_and_create_retry_task',
        queue='long',
        timeout=300,
        lead_name=lead_name,
        previous_task_name=task_name,
        attempt_number=attempt_number,
        enqueue_after_commit=True,
        job_name=f"retry_check_{lead_name}_{attempt_number}"
    )

def check_and_create_retry_task(lead_name, previous_task_name, attempt_number):
    """
    Check if the previous task status is 'Call Not Connected' and create retry task
    """
    try:
        # Get the previous task
        previous_task = frappe.get_doc("CRM Task", previous_task_name)
        
        # Check if task status is "Call Not Connected"
        if previous_task.status == "Call Not Connected":
            
            # Check if we haven't reached max attempts
            max_attempts = previous_task.get("custom_max_attempts", 10)
            
            if attempt_number < max_attempts:
                # Get the lead document
                lead_doc = frappe.get_doc("CRM Lead", lead_name)
                """Daily check for retry tasks - system date proof"""
                tasks = frappe.get_all("CRM Task",
                    filters={
                        "status": "Call Not Connected",
                        "due_date": ["<=", nowdate()]  # Check due date instead of scheduled time
                    }
                ),
                # Create new retry task
                new_attempt = attempt_number + 1
                retry_task = frappe.get_doc({
                    "doctype": "CRM Task",
                    "title": f"Retry Call - Attempt {new_attempt}",
                    "assigned_to": previous_task.assigned_to,
                    "status": "Todo",
                    "priority": "Medium",
                    "description": f"Retry task auto-created for lead {lead_name} - Attempt {new_attempt}/10",
                    "reference_doctype": "CRM Lead",
                    "reference_docname": lead_name,
                    "start_date": nowdate(),
                    "due_date": add_days(nowdate(), 0),
                    "custom_attempt_number": new_attempt,
                    "custom_max_attempts": max_attempts,
                    "custom_retry_interval_days": 2,
                    "custom_lead_name": lead_name,
                    "custom_previous_task": previous_task_name
                })
                
                retry_task.insert(ignore_permissions=True)
                
                # Create assignment
                if previous_task.assigned_to:
                    assignment = frappe.get_doc({
                        "doctype": "ToDo",
                        "allocated_to": previous_task.assigned_to,
                        "reference_type": "CRM Task",
                        "reference_name": retry_task.name,
                        "description": f"Retry task assigned: {retry_task.title}",
                        "priority": "Medium",
                        "status": "Open"
                    })
                    assignment.insert(ignore_permissions=True)
                
                # Schedule next retry check if not at max attempts
                if new_attempt < max_attempts:
                    schedule_retry_check(lead_name, retry_task.name, new_attempt)
                
                frappe.log_error(
                    message=f"Retry task {retry_task.name} created for lead {lead_name} - Attempt {new_attempt}",
                    title="Retry Task Created"
                )
            else:
                # Update lead status to Inactive/Dropped after max attempts
                lead_doc = frappe.get_doc("CRM Lead", lead_name)
                lead_doc.status = "Inactive / Dropped"
                lead_doc.add_comment(
                    "Comment",
                    f"Lead status automatically changed to 'Inactive / Dropped' after {max_attempts} unsuccessful contact attempts"
                )
                lead_doc.save(ignore_permissions=True)
                frappe.db.commit()
                
                frappe.log_error(
                    message=f"Maximum retry attempts ({max_attempts}) reached for lead {lead_name}. Status changed to Inactive/Dropped",
                    title="Max Retry Attempts Reached"
                )

                
        else:
            frappe.log_error(
                message=f"Task {previous_task_name} status is '{previous_task.status}', no retry needed",
                title="No Retry Needed"
            )
            
    except Exception as e:
        frappe.log_error(
            message=f"Error in retry task creation for lead {lead_name}: {str(e)}",
            title="Retry Task Creation Error"
        )
    
