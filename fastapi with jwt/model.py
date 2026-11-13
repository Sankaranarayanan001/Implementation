from pydantic import BaseModel


class ImageAnswer(BaseModel):
    question: str
    filename: str
    answer: str


class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    is_active: bool

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"