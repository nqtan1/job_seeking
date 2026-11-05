"""Failures a flow tool may raise: fixed codes, never exception text."""

from recruitai.core.errors import AppError


class ToolFailed(AppError):
    status_code = 502
    code = "tool_failed"
    default_detail = "This step could not finish."


class UrlNotAllowed(ToolFailed):
    code = "url_not_allowed"
    default_detail = "That address cannot be opened."


class NoJob(ToolFailed):
    code = "no_job"
    default_detail = "This step needs a job: pick one when you run it."


class RecipientNotAllowed(ToolFailed):
    code = "recipient_not_allowed"
    default_detail = "That address is not one you may email."


class EmailEmpty(ToolFailed):
    code = "email_empty"
    default_detail = "The email has no subject or no text."


class DailyLimit(ToolFailed):
    code = "daily_limit"
    default_detail = "You reached today's limit for this action."


class MessageEmpty(ToolFailed):
    code = "message_empty"
    default_detail = "There is no text to send."


class NotConnected(ToolFailed):
    code = "not_connected"
    default_detail = "Connect your account first (Automations, Connections)."


class ConnectionLost(ToolFailed):
    code = "connection_lost"
    default_detail = "That chat no longer accepts messages: connect it again."


class DeliveryUnknown(ToolFailed):
    code = "delivery_unknown"
    default_detail = (
        "The message may or may not have been delivered. Resume will not send it again."
    )


class SearchUnavailable(ToolFailed):
    code = "search_unavailable"
    default_detail = "Web search is not available right now."
