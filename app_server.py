from dataclasses import dataclass
import logging

from fastapi import FastAPI, HTTPException
from agent_framework_openai import OpenAIChatClient

logger = logging.getLogger(__name__)

app = FastAPI(title="Human-in-the-Loop Email Assistant", version="1.0.0")


@dataclass
class Email:
    sender: str
    subject: str
    body: str

    def __str__(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}"


class EmailAssistant:
    def __init__(self, chat_client: OpenAIChatClient) -> None:
        self.agent = chat_client.as_agent(
            name="Email Writer",
            instructions=(
                "You are an excellent email assistant. Your role is to respond to incoming emails. "
                "Be professional, clear, and concise."
            ),
        )

    async def process_email(self, email: Email) -> str:
        message = str(email)
        if email.sender == "sam@example.com":
            message = (
                "IMPORTANT EMAIL FROM KEY TEAM MEMBER. "
                "This email requires careful attention.\n\n"
                + message
            )

        result = await self.agent.run(message)
        return result.text

assistant = EmailAssistant(OpenAIChatClient())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
async def run_workflow() -> dict[str, str]:
    incoming_email = Email(
        sender="sam@example.com",
        subject="Urgent: Agent Framework Review Required",
        body=(
            "Hi Vince,\n\n"
            "Please review the latest agent framework updates and provide your feedback. "
            "This is critical for our Q4 roadmap. "
            "The changes include improvements to error handling and performance optimization.\n\n"
            "Can you review and provide feedback by end of week?\n\n"
            "Thanks,\nSam"
        ),
    )

    try:
        result = await assistant.process_email(incoming_email)
    except Exception as exc:
        logger.error(
            "Email processing failed (exception_type=%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Email processing failed.",
        ) from exc

    return {"response": result}
