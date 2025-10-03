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


@frappe.whitelist()
def check_all_pending_retry_tasks():
    """
    Daily scheduled job to check all tasks needing retry
    """
    try:
        # Get tasks WITHOUT attempt number filter - let create_retry_task handle it
        tasks = frappe.get_all("CRM Task",
            filters={
                "status": "Call Not Connected",
                "due_date": [">=", nowdate()],
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
                message=f"Lead {lead_name} moved to Unqualified after {max_attempts} attempts",
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
            "custom_attempt_number": str(new_attempt),
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


# ==========================================
# NEW FEATURES: NOT INTERESTED & INTERESTED
# ==========================================

def handle_task_status_change(doc, method=None):
    """
    Hook to handle when task status changes
    Triggered on CRM Task update
    """
    # Check if status changed
    if doc.has_value_changed("status"):
        old_status = doc.get_doc_before_save().status if doc.get_doc_before_save() else None
        new_status = doc.status
        
        # Handle "Not Interested" status
        if new_status == "Not Interested":
            handle_not_interested_status(doc)
        
        # Handle "Interested" status
        elif new_status == "Interested":
            handle_interested_status(doc)


def handle_not_interested_status(task_doc):
    """
    When task status is "Not Interested":
    1. Schedule email for 15 days (soft re-engagement)
    2. Schedule task for 30 days
    """
    try:
        lead_name = task_doc.custom_lead_name
        if not lead_name:
            return
        
        lead_doc = frappe.get_doc("CRM Lead", lead_name)
        
        # 1. Schedule email for 15 days later
        schedule_reengagement_email(
            lead_doc=lead_doc,
            task_doc=task_doc,
            days_after=15
        )
        
        # 2. Schedule task for 30 days later
        schedule_followup_task(
            lead_doc=lead_doc,
            task_doc=task_doc,
            title="Re-engage Not Interested Lead",
            days_after=30,
            description=f"Follow-up with lead who was 'Not Interested' 30 days ago. Previous task: {task_doc.name}"
        )
        
        # Add comment to lead
        lead_doc.add_comment(
            "Comment",
            f"Lead marked as 'Not Interested'. Email scheduled for {add_days(nowdate(), 15)}, Follow-up task scheduled for {add_days(nowdate(), 30)}"
        )
        lead_doc.save(ignore_permissions=True)
        
        frappe.msgprint(
            _("Not Interested workflow triggered: Email in 15 days, Task in 30 days"),
            alert=True,
            indicator="orange"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error handling Not Interested status for task {task_doc.name}: {str(e)}",
            title="Not Interested Handler Error"
        )


def handle_interested_status(task_doc):
    """
    When task status is "Interested":
    1. Send immediate email
    2. Schedule follow-up task for 2 days
    """
    try:
        lead_name = task_doc.custom_lead_name
        if not lead_name:
            return
        
        lead_doc = frappe.get_doc("CRM Lead", lead_name)
        
        # 1. Send immediate email
        send_interested_email(lead_doc, task_doc)
        
        # 2. Schedule follow-up task for 2 days
        schedule_followup_task(
            lead_doc=lead_doc,
            task_doc=task_doc,
            title="Follow-up with Interested Lead",
            days_after=2,
            description=f"Follow-up with interested lead. Previous task: {task_doc.name}"
        )
        
        # Add comment to lead
        lead_doc.add_comment(
            "Comment",
            f"Lead marked as 'Interested'. Welcome email sent, Follow-up task scheduled for {add_days(nowdate(), 2)}"
        )
        lead_doc.save(ignore_permissions=True)
        
        frappe.msgprint(
            _("Interested workflow triggered: Email sent, Follow-up task in 2 days"),
            alert=True,
            indicator="green"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error handling Interested status for task {task_doc.name}: {str(e)}",
            title="Interested Handler Error"
        )


def schedule_reengagement_email(lead_doc, task_doc, days_after=15):
    """
    Schedule a soft re-engagement email
    """
    try:
        # Create Email Queue entry scheduled for future
        email_queue = frappe.get_doc({
            "doctype": "Email Queue",
            "sender": frappe.db.get_single_value("System Settings", "email_footer_address") or "noreply@example.com",
            "recipients": lead_doc.email,
            "subject": "We'd Love to Hear from You Again",
            "message": get_reengagement_email_template(lead_doc),
            "reference_doctype": "CRM Lead",
            "reference_name": lead_doc.name,
            "send_after": add_days(now_datetime(), days_after),
            "status": "Not Sent"
        })
        email_queue.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.log_error(
            message=f"Re-engagement email scheduled for {lead_doc.name} on {add_days(nowdate(), days_after)}",
            title="Re-engagement Email Scheduled"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error scheduling re-engagement email: {str(e)}",
            title="Email Schedule Error"
        )


def send_interested_email(lead_doc, task_doc):
    """
    Send immediate email to interested lead
    """
    try:
        frappe.sendmail(
            recipients=[lead_doc.email],
            subject="Thank You for Your Interest!",
            message=get_interested_email_template(lead_doc),
            reference_doctype="CRM Lead",
            reference_name=lead_doc.name
        )
        
        frappe.log_error(
            message=f"Interested email sent to {lead_doc.name}",
            title="Interested Email Sent"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error sending interested email: {str(e)}",
            title="Email Send Error"
        )


def schedule_followup_task(lead_doc, task_doc, title, days_after, description):
    """
    Create a follow-up task scheduled for future
    """
    try:
        followup_task = frappe.get_doc({
            "doctype": "CRM Task",
            "title": title,
            "assigned_to": task_doc.assigned_to,
            "status": "Todo",
            "priority": "High",
            "description": description,
            "reference_doctype": "CRM Lead",
            "reference_docname": lead_doc.name,
            "start_date": add_days(nowdate(), days_after),
            "due_date": add_days(nowdate(), days_after),
            "custom_lead_name": lead_doc.name,
            "custom_previous_task": task_doc.name
        })
        
        followup_task.insert(ignore_permissions=True)
        
        # Create assignment
        if task_doc.assigned_to:
            assignment = frappe.get_doc({
                "doctype": "ToDo",
                "allocated_to": task_doc.assigned_to,
                "reference_type": "CRM Task",
                "reference_name": followup_task.name,
                "description": f"Follow-up task assigned: {followup_task.title}",
                "priority": "High",
                "status": "Open",
                "date": add_days(nowdate(), days_after)
            })
            assignment.insert(ignore_permissions=True)
        
        frappe.db.commit()
        
        frappe.log_error(
            message=f"Follow-up task {followup_task.name} scheduled for {add_days(nowdate(), days_after)}",
            title="Follow-up Task Created"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error creating follow-up task: {str(e)}",
            title="Task Creation Error"
        )


def get_reengagement_email_template(lead_doc):
    """
    Soft re-engagement email template
    """
    return f"""
    <p>Dear {lead_doc.first_name or 'Valued Customer'},</p>
    
    <p>We noticed you showed interest in our services a couple of weeks ago.</p>
    
    <p>We understand that timing is everything, and we'd love to reconnect with you to see if there's anything we can help you with now.</p>
    
    <p>If you have any questions or would like to discuss how we can support you, please don't hesitate to reach out.</p>
    
    <p>Looking forward to hearing from you!</p>
    
    <p>Best regards,<br>
    Your Team</p>
    """


def get_interested_email_template(lead_doc):
    """
    Interested lead email template
    """
    return f"""
    <p>Dear {lead_doc.first_name or 'Valued Customer'},</p>
    
    <p>Thank you so much for expressing interest in our services!</p>
    
    <p>We're excited to have the opportunity to work with you and help you achieve your goals.</p>
    
    <p>One of our team members will follow up with you within the next 2 days to discuss the next steps.</p>
    
    <p>In the meantime, if you have any questions, please feel free to reach out.</p>
    
    <p>Best regards,<br>
    Your Team</p>
    """
@frappe.whitelist()
def create_callback_task(task_name, callback_datetime, notes=None):
    """
    Create a callback task for scheduled date/time
    """
    try:
        # Get the original task
        original_task = frappe.get_doc("CRM Task", task_name)
        
        # Update original task with callback datetime
        original_task.custom_callback_datetime = callback_datetime
        original_task.save(ignore_permissions=True)
        
        # Create new callback task
        callback_task = frappe.get_doc({
            "doctype": "CRM Task",
            "title": f"Scheduled Callback - {original_task.title}",
            "assigned_to": original_task.assigned_to,
            "status": "Todo",
            "priority": "High",
            "description": f"Scheduled callback task.\n\nOriginal task: {task_name}\n\nNotes: {notes or 'No additional notes'}",
            "reference_doctype": "CRM Lead",
            "reference_docname": original_task.custom_lead_name,
            "start_date": frappe.utils.getdate(callback_datetime),
            "due_date": frappe.utils.getdate(callback_datetime),
            "custom_callback_date__time": callback_datetime,
            "custom_lead_name": original_task.custom_lead_name,
            "custom_previous_task": task_name,
            "custom_callback_notification_sent": 0
        })
        
        callback_task.insert(ignore_permissions=True)
        
        # Create ToDo assignment
        if original_task.assigned_to:
            assignment = frappe.get_doc({
                "doctype": "ToDo",
                "allocated_to": original_task.assigned_to,
                "reference_type": "CRM Task",
                "reference_name": callback_task.name,
                "description": f"Scheduled callback at {frappe.utils.format_datetime(callback_datetime)}",
                "priority": "High",
                "status": "Open",
                "date": frappe.utils.getdate(callback_datetime)
            })
            assignment.insert(ignore_permissions=True)
        
        # Add comment to lead
        if original_task.custom_lead_name:
            lead_doc = frappe.get_doc("CRM Lead", original_task.custom_lead_name)
            lead_doc.add_comment(
                "Comment",
                f"Callback scheduled for {frappe.utils.format_datetime(callback_datetime)}. Task: {callback_task.name}"
            )
            lead_doc.save(ignore_permissions=True)
        
        frappe.db.commit()
        
        frappe.log_error(
            message=f"Callback task {callback_task.name} created for {callback_datetime}",
            title="Callback Task Created"
        )
        
        return {
            "success": True,
            "task_name": callback_task.name,
            "callback_datetime": callback_datetime
        }
        
    except Exception as e:
        frappe.log_error(
            message=f"Error creating callback task: {str(e)}",
            title="Callback Task Creation Error"
        )
        return {"success": False, "error": str(e)}


def send_callback_notifications():
    """
    Scheduled function to send notifications 1 hour before callback
    Run this every hour via scheduler
    """
    try:
        # Get current time
        current_time = now_datetime()
        
        # Get time 1 hour from now (notification window)
        notification_time_start = add_to_date(current_time, hours=1)
        notification_time_end = add_to_date(current_time, hours=1, minutes=30)  # 30 min window
        
        # Find tasks scheduled in the next hour that haven't been notified
        upcoming_callbacks = frappe.get_all("CRM Task",
            filters={
                "custom_callback_date__time": ["between", [notification_time_start, notification_time_end]],
                "custom_callback_notification_sent": 0,
                "status": ["!=", "Completed"]
            },
            fields=["name", "title", "assigned_to", "custom_callback_date__time", "custom_lead_name"]
        )
        
        frappe.log_error(
            message=f"Found {len(upcoming_callbacks)} upcoming callbacks to notify",
            title="Callback Notifications Check"
        )
        
        # Send notification for each task
        for task in upcoming_callbacks:
            send_callback_reminder_notification(task)
            
    except Exception as e:
        frappe.log_error(
            message=f"Error in callback notification check: {str(e)}",
            title="Callback Notification Error"
        )


def send_callback_reminder_notification(task_data):
    """
    Send notification reminder for upcoming callback
    """
    try:
        task_doc = frappe.get_doc("CRM Task", task_data['name'])
        
        # Format callback time
        callback_time = frappe.utils.format_datetime(task_data['custom_callback_date__time'], "dd MMM yyyy, hh:mm a")
        
        # Create notification
        notification = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": f"🔔 Callback Reminder: {task_data['title']}",
            "for_user": task_data['assigned_to'],
            "type": "Alert",
            "document_type": "CRM Task",
            "document_name": task_data['name'],
            "email_content": f"""
                <p><strong>Reminder:</strong> You have a scheduled callback in 1 hour!</p>
                <p><strong>Time:</strong> {callback_time}</p>
                <p><strong>Task:</strong> {task_data['title']}</p>
                <p><strong>Lead:</strong> {task_data.get('custom_lead_name', 'N/A')}</p>
                <p>Please prepare for the callback.</p>
            """
        })
        notification.insert(ignore_permissions=True)
        
        # Send email notification
        if task_data['assigned_to']:
            user_email = frappe.db.get_value("User", task_data['assigned_to'], "email")
            
            if user_email:
                frappe.sendmail(
                    recipients=[user_email],
                    subject=f"Callback Reminder: {task_data['title']}",
                    message=f"""
                        <h3>Callback Reminder</h3>
                        <p>You have a scheduled callback in <strong>1 hour</strong>!</p>
                        <ul>
                            <li><strong>Time:</strong> {callback_time}</li>
                            <li><strong>Task:</strong> {task_data['title']}</li>
                            <li><strong>Lead:</strong> {task_data.get('custom_lead_name', 'N/A')}</li>
                        </ul>
                        <p>Please prepare for the callback.</p>
                        <p><a href="{frappe.utils.get_url()}/app/crm-task/{task_data['name']}">View Task</a></p>
                    """,
                    reference_doctype="CRM Task",
                    reference_name=task_data['name']
                )
        
        # Mark notification as sent
        task_doc.custom_callback_notification_sent = 1
        task_doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.log_error(
            message=f"Callback reminder sent for task {task_data['name']} to {task_data['assigned_to']}",
            title="Callback Reminder Sent"
        )
        
    except Exception as e:
        frappe.log_error(
            message=f"Error sending callback reminder for task {task_data['name']}: {str(e)}",
            title="Callback Reminder Error"
        )
