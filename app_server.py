from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from agent_framework_openai import OpenAIChatClient
from pydantic import BaseModel

app = FastAPI(title="Human-in-the-Loop Email Assistant", version="1.0.0")


@dataclass
class Email:
    sender: str
    subject: str
    body: str

    def __str__(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}"


class EmailRequest(BaseModel):
    sender: str
    subject: str
    body: str


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


@app.get("/")
async def root() -> dict[str, str | dict]:
    return {
        "name": "Human-in-the-Loop Email Assistant",
        "version": "1.0.0",
        "description": "An email assistant workflow that processes emails and provides responses",
        "endpoints": {
            "GET /health": "Health check endpoint",
            "POST /run": "Run the email assistant workflow",
            "GET /docs": "Interactive API documentation (Swagger UI)",
            "GET /redoc": "ReDoc API documentation",
        },
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
async def run_workflow(request: EmailRequest) -> dict[str, str]:
    incoming_email = Email(
        sender=request.sender,
        subject=request.subject,
        body=request.body,
    )

    try:
        result = await assistant.process_email(incoming_email)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error processing email: {exc}") from exc

    return {"response": result}
