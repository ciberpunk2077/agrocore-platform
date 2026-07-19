from uuid import UUID

from ninja import Schema
from pydantic import EmailStr
# from pydantic import ConfigDict


class UserSchema(Schema):
    # id: str
    # # email: str
    # email: EmailStr
    # first_name: str
    # last_name: str

    # model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str

class LoginSchema(Schema):
    # email: str
    email: EmailStr
    password: str

# class LoginResponseSchema(Schema):
#     message: str
#     user: UserSchema

class LoginResponseSchema(Schema):
    access: str
    refresh: str
    user: UserSchema