from pydantic import BaseModel, ConfigDict, Field, StrictInt


class TelegramUser(BaseModel):
    id: StrictInt

    model_config = ConfigDict(extra="ignore")


class TelegramPhotoSize(BaseModel):
    file_id: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(extra="ignore")


class TelegramDocument(BaseModel):
    file_id: str = Field(min_length=1, max_length=255)
    file_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="ignore")


class TelegramChat(BaseModel):
    id: StrictInt

    model_config = ConfigDict(extra="ignore")


class TelegramMessage(BaseModel):
    from_user: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat | None = None
    text: str | None = Field(default=None, max_length=4096)
    caption: str | None = Field(default=None, max_length=1024)
    photo: list[TelegramPhotoSize] = Field(default_factory=list, max_length=10)
    document: TelegramDocument | None = None

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TelegramUpdate(BaseModel):
    update_id: StrictInt = Field(ge=0)
    message: TelegramMessage | None = None

    model_config = ConfigDict(extra="ignore")
