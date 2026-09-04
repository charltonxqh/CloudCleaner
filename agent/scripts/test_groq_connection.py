import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq


load_dotenv("../.env")


def main():
    model = ChatGroq(
        model=os.environ["GROQ_MODEL"],
        temperature=0,
    )

    response = model.invoke(
        "Reply with exactly: CloudCleaner Groq connection successful"
    )

    print(response.content)


if __name__ == "__main__":
    main()