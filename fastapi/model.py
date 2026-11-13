from pydantic import BaseModel


class ImageAnswer(BaseModel):
    question: str
    filename: str
    answer: str