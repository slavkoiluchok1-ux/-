from pydantic import BaseModel, Field

class Item(BaseModel):
    id: int = Field(..., description="The unique identifier for the item.", example=1)
    name: str = Field(..., max_length=50, description="The name of the item.", example="Sample Item")
    description: str | None = Field(None, description="The description of the item.", example="A sample item for demonstration purposes.")