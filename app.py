import streamlit as st
import re
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain.indexes.vectorstore import VectorStoreIndexWrapper
from langchain.vectorstores import Chroma 
from langchain_openai import OpenAI
from langchain_openai.embeddings import OpenAIEmbeddings
from dotenv import load_dotenv, find_dotenv
import os
load_dotenv(find_dotenv())
# OpenAI API Key (use your key or secrets)

openai_api_key = os.environ["OPENAI_API_KEY"] # st.secrets.get("openai_api_key", "your_openai_api_key")
llm = ChatOpenAI(temperature=0.7, model="gpt-4o-mini", openai_api_key=openai_api_key)
persist_directory = "embedding/chroma"
embedding = OpenAIEmbeddings()
vectorstore = Chroma(persist_directory=persist_directory, embedding_function=embedding)

index = VectorStoreIndexWrapper(vectorstore=vectorstore)
# Check if URL is an Amazon URL
def is_amazon_url(url):
    amazon_pattern = r"(https?://)?(www\.)?amazon\.[a-z]{2,3}(/[\S]*)?"
    return bool(re.match(amazon_pattern, url, re.IGNORECASE))

# Initialize session state
if "url_verified" not in st.session_state:
    st.session_state.url_verified = False

if not st.session_state.url_verified:
    st.title("Enter Amazon URL")
    
    # Text box for URL input
    user_url = st.text_input("Paste an Amazon URL here:")

    if user_url:
        if is_amazon_url(user_url):
            st.success("Valid Amazon URL! Redirecting to chatbot...")
            st.session_state.url_verified = True
            products = vectorstore.search("", search_type="similarity", filter={"source": user_url}, k=1)
            product_names = [product.metadata['title'] for product in products]
            st.session_state.products = product_names
        else:
            st.error("Invalid URL. Please enter a valid Amazon URL.")

if st.session_state.url_verified:
    st.title("Amazon Chatbot")

    # Initialize session state for chat history
    if "messages" not in st.session_state:
        st.session_state.messages = [
            SystemMessage(
                content = (
                    "You are a helpful assistant that provides information about Amazon products. "
                    f"The user has searched for the following product: {st.session_state.products} "
                    "Provide answers considering this product and other related Amazon products. "
                    "Do not provide information that is not related to the product or other Amazon products. "
                    "Only provide information that can be evidenced by the search results. Do not make up information. "
                    "Try to provide short and concise answers, and give links to related Amazon products. "
                )
            )
        ]

    # Display chat history
    for msg in st.session_state.messages:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg.content)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg.content)

    # User input box for chat
    if user_input := st.chat_input("Type your message here..."):
        # Add user message to the chat history
        st.session_state.messages.append(HumanMessage(content=user_input))
        with st.chat_message("user"):
            st.markdown(user_input)

        # Get AI response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            # query = "Which keyboards has USB-C charging?"
            result = index.query_with_sources(user_input, llm=OpenAI())
            # print(result["answer"])
            # print(result["sources"])
            st.session_state.messages.append(SystemMessage(content=f"Retrieval has found: {result['answer']} \n Sources: {result['sources']}"))
            assistant_response = llm(st.session_state.messages)
            message_placeholder.markdown(assistant_response.content)

        # Append the assistant's message to chat history
        st.session_state.messages.append(AIMessage(content=assistant_response.content))
