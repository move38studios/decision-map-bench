from dotenv import load_dotenv
from typesafe_sdk import Noul, TypeSafeClient

load_dotenv()

with TypeSafeClient() as client:
    print("Models:", client.models.list())

    response = client.system_one(
        state="Hi, my integration has been failing for 3 days and I'm losing sales. Please help ASAP.",
        questions={"is_urgent": Noul(instructions="The message conveys urgency")},
    )
    print("Model used:", response.model)
    print("is_urgent:", response.answers["is_urgent"].noul)
    print("Usage:", response.usage)
