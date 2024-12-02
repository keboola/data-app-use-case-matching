import json
import streamlit as st
from openai import OpenAI
import requests
from bs4 import BeautifulSoup, Comment
from kbcstorage.client import Client
import csv
import streamlit.components.v1 as components
import os
import pandas as pd

openai_token = st.secrets["openai_token"]
kbc_url = st.secrets["kbc_url"]
kbc_token = st.secrets["keboola_token"]
client = Client(kbc_url, kbc_token)

LOGO_IMAGE_PATH = os.path.abspath("./app/static/keboola.png")

# Setting page config
st.set_page_config(page_title="Use case matching")


@st.cache_data(ttl=60, show_spinner=False)
def hide_custom_anchor_link():
    st.markdown(
        """
        <style>
            /* Hide anchors directly inside custom HTML headers */
            h1 > a, h2 > a, h3 > a, h4 > a, h5 > a, h6 > a {
                display: none !important;
            }
            /* If the above doesn't work, it may be necessary to target by attribute if Streamlit adds them dynamically */
            [data-testid="stMarkdown"] h1 a, [data-testid="stMarkdown"] h3 a,[data-testid="stMarkdown"] h5 a,[data-testid="stMarkdown"] h2 a {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60, show_spinner=False)
def display_footer_section():
    # Inject custom CSS for alignment and style
    st.markdown(
        """
        <style>
            .footer {
                width: 100%;
                font-size: 14px;  /* Adjust font size as needed */
                color: #22252999;  /* Adjust text color as needed */
                padding: 10px 0;  /* Adjust padding as needed */
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .footer p {
                margin: 0;  /* Removes default margin for p elements */
                padding: 0;  /* Ensures no additional padding is applied */
            }
        </style>
        <div class="footer">
            <p>© Keboola 2024</p>
            <p>Version 1.0</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ChangeButtonColour(widget_label, font_color, background_color, border_color):
    htmlstr = f"""
        <script>
            var elements = window.parent.document.querySelectorAll('button');
            for (var i = 0; i < elements.length; ++i) {{ 
                if (elements[i].innerText == '{widget_label}') {{ 
                    elements[i].style.color ='{font_color}';
                    elements[i].style.background = '{background_color}';
                    elements[i].style.borderColor = '{border_color}';
                }}
            }}
        </script>
        """
    components.html(f"{htmlstr}", height=0, width=0)


def get_dataframe(table_name):
    """
    Reads the provided table from the specified table in Keboola Connection.

    Args:
        table_name (str): The name of the table to write the data to.

    Returns:
        The table as dataframe
    """
    table_detail = client.tables.detail(table_name)
    client.tables.export_to_file(table_id=table_name, path_name="")
    list = client.tables.list()
    with open("./" + table_detail["name"], mode="rt", encoding="utf-8") as in_file:
        lazy_lines = (line.replace("\0", "") for line in in_file)
        reader = csv.reader(lazy_lines, lineterminator="\n")
    if os.path.exists("data.csv"):
        os.remove("data.csv")
    else:
        print("The file does not exist")
    os.rename(table_detail["name"], "data.csv")
    data = pd.read_csv("data.csv")
    return data


def get_openai_response(ai_setup, prompt, api_key):
    """
    Writes the provided data to the specified table in Keboola Connection,
    updating existing records as needed.

    Args:
        ai_setup (str): The instructions to send to OpenAI. In case of a conversation this is instructions for the system.
        prompt (str): In case of a conversation this is instructions for the user.
        api_key (str): OpenAI API key

    Returns:
        The text from the response from OpenAI
    """

    open_ai_client = OpenAI(
        api_key=api_key,
    )
    messages = [{"role": "system", "content": ai_setup}]
    if prompt:
        messages.append({"role": "user", "content": prompt})

    try:
        completion = open_ai_client.chat.completions.create(
            model="gpt-3.5-turbo", messages=messages, temperature=0.7
        )

        message = completion.choices[0].message.content

        # Extracting the text response from the response object
        return message

    except Exception as e:
        return f"An error occurred: {e}"


# Function to get use cases from the webpage
def get_use_cases_from_webpage(url, type):
    # Fetch the webpage content
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Failed to retrieve the webpage content")

    soup = BeautifulSoup(response.content, 'html.parser')

    # Remove comments
    for comment in soup.findAll(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove unnecessary tags
    for tag in soup.findAll(['script', 'style', 'head']):
        tag.decompose()
    # Remove unnecessary attributes
    for tag in soup.findAll(True):
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in ['href']:
                del tag.attrs[attr]

    # Get the raw HTML content of the body
    html_body = soup.decode_contents()

    # Define a prompt to extract use cases from the text content
    prompt = (f"list all the titles and href values for {type} from the text below\n    " +
              """return a response as a json with the following format:\n
            [{'title': 'the title',
            'url':'the href value. if the value starts with / then add the domain of the website before it'}]
            \n
            return just that. follow the format strictly\n
            remember to return a valid json\n\n""" + f"text:\n\n{html_body}")

    # Use OpenAI to generate the use cases
    response = get_openai_response(prompt, None, openai_token)
    print(response)
    return json.loads(response)


# Function to match the best use case to a lead
def match_use_case(lead_info, use_cases):
    prompt = ("""You will get lead information and a json of use cases. Match the best use case for for the lead.
            return a json of the following format:\n
            {
            'email':'the email of the lead',
            'use_case': 'the title of the use case',
            'url': 'the url of the use case
            }\n
            follow the format strictly\n
            remember to return a valid json\n""" + f"lead information:\n{lead_info}\n\nAvailable use cases:\n{use_cases}")
    response = get_openai_response(prompt, None, openai_token)
    return json.loads(response)


# Function to generate a personalized email
def generate_email(lead_info, use_case):
    prompt = f"Generate a personalized email for the following lead information:\n{lead_info}\n\nSuggested use case:\n{use_case}"
    response = get_openai_response(prompt, None, openai_token)
    return response


def generate_sms(lead_info, use_case):
    prompt = f"Generate a personalized sms for the following lead information:\n{lead_info}\n\nSuggested use case:\n{use_case}"
    response = get_openai_response(prompt, None, openai_token)
    return response


def generate_li(lead_info, use_case):
    prompt = f"Generate a personalized linkedin message for the following lead information:\n{lead_info}\n\nSuggested use case:\n{use_case}"
    response = get_openai_response(prompt, None, openai_token)
    return response


# Function to add a new text input
def add_text_input():
    st.session_state.url_list.append("")
    st.session_state.url_type_list.append("")


# Function to remove the last text input
def remove_text_input():
    if len(st.session_state.url_list) > 1:
        st.session_state.url_list.pop()
        st.session_state.url_type_list.pop()


# Streamlit app
st.image(LOGO_IMAGE_PATH)
hide_img_fs = """
        <style>
        button[title="View fullscreen"]{
            visibility: hidden;}
        </style>
        """
st.markdown(hide_img_fs, unsafe_allow_html=True)
title, download_all = st.columns([5, 1])
st.title("Marketing content generator")

progress_container = st.container()
urls, types = st.columns([3, 1])
with urls:
    # use_case_url = st.text_input('Use Cases URL')
    # Initialize session state for storing text inputs
    if 'url_list' not in st.session_state:
        st.session_state.url_list = [""]
        st.session_state.url_type_list = [""]
    any_filled = False
    type_filled = True
    url_col, type_col = st.columns([3, 1])
    url_col.write('URL')
    type_col.markdown('Type', help='Write what can I find in this url (use cases, customer stories, etc.)')
    for i, url in enumerate(st.session_state.url_list):
        st.session_state.url_list[i] = url_col.text_input(f'URL {i + 1}', value=url, label_visibility='collapsed')
        st.session_state.url_type_list[i] = type_col.text_input(f'Type {i + 1}', value=url,
                                                                label_visibility='collapsed')
        if st.session_state.url_list[i] and st.session_state.url_type_list[i]:
            any_filled = True
        if st.session_state.url_list[i] and (not st.session_state.url_type_list[i]):
            type_filled = False
        if (not st.session_state.url_list[i]) and st.session_state.url_type_list[i]:
            type_filled = False
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add URL"):
            add_text_input()
        ChangeButtonColour("Add URL", "#FFFFFF", "#1EC71E", "#1EC71E")
    with col2:
        if len(st.session_state.url_list) > 1:
            if st.button("Remove URL"):
                remove_text_input()
            ChangeButtonColour("Remove URL", "#FFFFFF", "#1EC71E", "#1EC71E")

with types:
    st.text('Generate:')
    email_checkbox = st.checkbox('Email', value=True)
    sms_checkbox = st.checkbox('SMS', value=True)
    li_checkbox = st.checkbox('LinkedIN DM', value=True)

if types.button("Generate"):
    if not any_filled:
        st.error('Please fill in at least one url', icon="🚨")
    elif not type_filled:
        st.error('Please fill in all pairs of url-type', icon="🚨")
    else:
        use_cases = []
        progress_bar = progress_container.progress(0)
        status_text = progress_container.text('Generating... 0% Done')
        for url, type in zip(st.session_state.url_list, st.session_state.url_type_list):
            if url:
                use_cases = use_cases + get_use_cases_from_webpage(url, type)
                progress_bar.progress(((i + 1) / len(st.session_state.url_list)) / 2)
                status_text.text(f"Generating... {round((i + 1) / len(st.session_state.url_list) * 50, 1)}% Done")
        use_cases_json = json.dumps(use_cases)
        # leads = [{'name': 'Leonid Ler', 'company': 'Bytegarden', 'email': 'leon.ler@bytegarden.com'}]
        leads = get_dataframe('in.c-keboola-ex-google-drive-1156976755.SF-Leads-Example-Sheet1')

        for index, lead in leads.iterrows():
            lead_info = f"Name: {lead['First_Name']} {lead['Last_Name']}, Company: {lead['Company']}, Email: {lead['Email']}"
            best_use_case = match_use_case(lead_info, use_cases_json)
            personalized_email = generate_email(lead_info, json.dumps(best_use_case))
            personalized_sms = generate_sms(lead_info, json.dumps(best_use_case))
            personalized_li = generate_li(lead_info, json.dumps(best_use_case))

            if email_checkbox:
                st.write(f"Generated email for {lead['First_Name']} {lead['Last_Name']}:")
                st.write(personalized_email)
            if sms_checkbox:
                st.write(f"Generated sms for {lead['First_Name']} {lead['Last_Name']}:")
                st.write(personalized_sms)
            if li_checkbox:
                st.write(f"Generated li for {lead['First_Name']} {lead['Last_Name']}:")
                st.write(personalized_li)
            progress_bar.progress(0.5 + ((index + 1) / len(leads)) / 2)
            status_text.text(f"Generating... {round(50 + (index + 1) / len(leads) * 50, 1)}% Done")
        status_text.text(f"Content Generated and saved to the source system")
        progress_container.download_button(
            label="Download all as csv",
            data=leads.to_csv(index=False).encode('utf-8'),
            file_name='cv_analysis.csv',
            mime="text/csv"
        )
        ChangeButtonColour("Download all as csv", "#FFFFFF", "#1EC71E", "#1EC71E")
ChangeButtonColour("Generate", "#FFFFFF", "#1EC71E", "#1EC71E")

display_footer_section()
