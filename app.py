import streamlit as st
import re
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.indexes.vectorstore import VectorStoreIndexWrapper
from langchain.vectorstores import Chroma
from streamlit_cookies_manager import EncryptedCookieManager
from langchain_openai.embeddings import OpenAIEmbeddings
import os
import sqlite3
import hashlib

# Initialize SQLite database for user management and usage tracking
conn = sqlite3.connect("user_management.db")
cursor = conn.cursor()

# Create table for storing user credentials
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT
)
""")

# Create table for tracking user interactions
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_usage (
    username TEXT PRIMARY KEY,
    usage_count INTEGER
    last_reset_date TEXT
)
""")
conn.commit()

# Function to create a new user (sign up)
def create_user(username, password):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()  # Hash the password for security
    cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
    conn.commit()

# Function to authenticate an existing user (login)
def authenticate_user(username, password):
    cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    if result:
        stored_password_hash = result[0]
        return stored_password_hash == hashlib.sha256(password.encode()).hexdigest()
    return False

# Function to track usage
from datetime import datetime

# Function to track usage and reset daily
def use_app(username):
    # Get the current date
    current_date = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("SELECT usage_count, last_reset_date FROM user_usage WHERE username = ?", (username,))
    result = cursor.fetchone()

    if result:
        usage_count, last_reset_date = result
    else:
        # If the user is new, initialize their usage count and reset date
        usage_count = 0
        last_reset_date = current_date
        cursor.execute("INSERT INTO user_usage (username, usage_count, last_reset_date) VALUES (?, ?, ?)", 
                       (username, usage_count, last_reset_date))
        conn.commit()

    # Check if the reset date has changed (new day)
    if last_reset_date != current_date:
        # Reset usage count for the new day
        usage_count = 0
        cursor.execute("UPDATE user_usage SET usage_count = ?, last_reset_date = ? WHERE username = ?",
                       (usage_count, current_date, username))
        conn.commit()

    # Allow up to 10 interactions
    if usage_count < 10:
        usage_count += 1
        cursor.execute("UPDATE user_usage SET usage_count = ? WHERE username = ?", (usage_count, username))
        conn.commit()
        return True, usage_count
    else:
        return False, usage_count


os.environ["COOKIE_PASSWORD"] = st.secrets.get("COOKIE_PASSWORD", None)

# Initialize cookies manager
cookies = EncryptedCookieManager(password=os.environ.get("COOKIE_PASSWORD", "default_password"))

# Check if cookies are ready
if not cookies.ready():
    st.stop()

# Check for login status
is_logged_in = cookies.get("is_logged_in", "False")
current_user = cookies.get("current_user", "None")

# Initialize OpenAI and other app setup
os.environ["OPENAI_API_KEY"] = st.secrets.get("OPENAI_API_KEY", None)
openai_api_key = os.environ["OPENAI_API_KEY"]
llm = ChatOpenAI(temperature=0.7, model="gpt-4o-mini", openai_api_key=openai_api_key)
persist_directory = "embedding/chroma"
embedding = OpenAIEmbeddings()
vectorstore = Chroma(persist_directory=persist_directory, embedding_function=embedding)
index = VectorStoreIndexWrapper(vectorstore=vectorstore)

# Main app logic
if is_logged_in == "False":
    # If user is not logged in and hasn't exceeded 10 interactions, allow them to interact
    st.title("Login / Sign Up")

    # Sign up form
    with st.form("Sign Up Form"):
        signup_username = st.text_input("Username")
        signup_password = st.text_input("Password", type="password")
        signup_button = st.form_submit_button("Create Account")
        if signup_button:
            create_user(signup_username, signup_password)
            st.success("Account created! You can now log in.")

    # Login form
    with st.form("Login Form"):
        login_username = st.text_input("Username (for login)")
        login_password = st.text_input("Password (for login)", type="password")
        login_button = st.form_submit_button("Login")
        if login_button:
            if authenticate_user(login_username, login_password):
                cookies["is_logged_in"] = "True"  # Store as string
                cookies["current_user"] = login_username
                cookies.save()
            else:
                st.error("Invalid username or password.")
        if st.form_submit_button("Logout"):
            cookies["is_logged_in"] = "False"  # Store as string
            cookies["current_user"] = "None"
            cookies.save()
        # # When logging out
        # if st.button("Logout"):
        #     cookies["is_logged_in"] = "False"  # Store as string
        #     cookies["current_user"] = "None"
        #     cookies.save()

else:
    # User is logged in
    st.title(f"Welcome, {current_user}!")

    # Track the number of interactions
    can_use, usage_count = use_app(current_user)
    if not can_use:
        st.warning(f"You have reached your limit of 10 interactions. Please log out.")
    else:
        st.write(f"Usage count: {usage_count} / 10")

    # Allow Amazon URL input and chatbot interaction
    if usage_count < 10:
        if "url_verified" not in st.session_state:
            st.session_state.url_verified = False

        if not st.session_state.url_verified:
            st.title("Enter Amazon URL")
            user_url = st.text_input("Paste an Amazon URL here:")

            if user_url:
                amazon_pattern = r"(https?://)?(www\.)?(amazon|amzn)\.[a-z]{2,3}(/[\S]*)?"
                if re.match(amazon_pattern, user_url):
                    st.success("Valid Amazon URL! Redirecting to chatbot...")
                    st.session_state.url_verified = True
                else:
                    st.error("Invalid URL. Please enter a valid Amazon URL.")

        if st.session_state.url_verified:
            # Chatbot functionality
            st.title("Amazon Chatbot")
            if "messages" not in st.session_state:
                st.session_state.messages = [
                    SystemMessage(content="You are a helpful assistant for Amazon products.")
                ]

            for msg in st.session_state.messages:
                if isinstance(msg, HumanMessage):
                    with st.chat_message("user"):
                        st.markdown(msg.content)
                elif isinstance(msg, AIMessage):
                    with st.chat_message("assistant"):
                        st.markdown(msg.content)

            if user_input := st.chat_input("Type your message here..."):
                st.session_state.messages.append(HumanMessage(content=user_input))
                with st.chat_message("user"):
                    st.markdown(user_input)

                result = index.query_with_sources(user_input, llm=ChatOpenAI(model="gpt-4o-mini"))
                st.session_state.messages.append(SystemMessage(content=f"Retrieval has found: {result['answer']} \n Sources: {result['sources']}"))
                assistant_response = llm(st.session_state.messages)
                st.session_state.messages.append(AIMessage(content=assistant_response.content))
                with st.chat_message("assistant"):
                    st.markdown(assistant_response.content)
    # if st.form_submit_button("Logout"):
    #     cookies["is_logged_in"] = "False"  # Store as string
    #     cookies["current_user"] = "None"
    #     cookies.save()

    if st.button("Logout"):
        cookies["is_logged_in"] = "False"
        cookies["current_user"] = "None"
        cookies.save()

# Close the database connection
conn.close()
