import os
import re
import time
import pickle
import telebot
from jira import JIRA
from funcy import pluck
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.types import ASGIApp

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
JIRA_LINK = os.getenv('JIRA_LINK')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_TOKEN = os.getenv('JIRA_TOKEN')
ALLOWED_KEYS = os.getenv('ALLOWED_KEYS').split(',')
TRANSITION_ID = os.getenv('TRANSITION_ID')
TRANSITION_TEST_ID = os.getenv('TRANSITION_TEST_ID')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
jira = JIRA(server=JIRA_LINK,basic_auth=(JIRA_EMAIL, JIRA_TOKEN))

PROJECTS = jira.projects()
LIST_PROJECTS = (project.raw for project in PROJECTS)
NAME_RPOJECTS = sorted(project.name for project in PROJECTS)
KEYS_PROJECTS = sorted(project.key for project in PROJECTS)

app = FastAPI()

@app.middleware("http")
async def check_request(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    skey = request.query_params.get("skey")
    if skey == None or skey not in ALLOWED_KEYS:
        return Response("Unauthorized", status_code=401)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

def extract_arg(arg):
    return arg.split()[1:]

@app.get("/")
def read_main():
    return Response("Unauthorized", status_code=401)

@app.get("/projects")
def read_root():
    return {"PROJECTS": LIST_PROJECTS}

@app.get('/prs')
def get_prs():
    text = "Вот список проектов:"
    for project in PROJECTS:
        text += "\n" + project.name + "(" + project.key + ")"
    return {"prs": text}

@app.get('/info/{project_key}')
def read_issues(project_key: str, q: Optional[str] = None):
    try:
        issues = jira.search_issues(jql_str='project=' + project_key, maxResults=100)
        return {"issues": (issue.raw for issue in issues)}
    except:
        return {"issues": null}

@app.post('/check/{issue_id}')
def check_and_send_issue(issue_id: str):
    try:
        issue = jira.issue(issue_id)
        url = JIRA_LINK + "/browse/" + issue.key
        if issue.fields.status.name == 'На проверку':
            text = 'Задача <a href="' + url +'">' + issue.fields.summary + " (" + issue.fields.project.name + ", " + issue.key + ")</a> отправлена на проверку"
        elif issue.fields.status.name == 'Done':
            text = 'Задача <a href="' + url +'">' + issue.fields.summary + " (" + issue.fields.project.name + ", " + issue.key + ")</a> решена"
        else:
            text = 'Изменение задачи <a href="' + url +'">' + issue.fields.summary + " (" + issue.fields.project.name + ", " + issue.key + ")</a>:"
            text += "\nСтатус:" + issue.fields.status.name
            description = issue.fields.description if issue.fields.description else "Отсутствует"
            text += "\nОписание:\n" + re.sub("^\s+|\n|\r|\s+$", '', description)
        bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Html", disable_web_page_preview=True)
    except:
        bot.send_message(chat_id=CHAT_ID, text="Проверьте вебхук на изменение задачи...")

@app.get('/send/{project_key}')
def send_issues(project_key: str):
    issues = jira.search_issues(jql_str='project=' + project_key + ' and status not in (Done)', maxResults=100)
    if len(issues) > 0:
        text = 'Вот текущие задачи:'
        for idx, issue in enumerate(issues, start=1):
            url = JIRA_LINK + "/browse/" + issue.key
            name = '<a href="' + url + '">' + issue.fields.summary + " (" + issue.fields.project.name + ", " + issue.key + ")" + "</a>"
            text += "\n" + str(idx) + ". " + name
            if issue.fields.description:
                description = issue.fields.description if issue.fields.description else "Отсутствует"
                text += "\nОписание:\n" + re.sub("^\s+|\n|\r|\s+$", '', description)
            text += "\n"
    else:
        text = 'Задачи отсутствуют'
    bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Html", disable_web_page_preview=True)

@app.get("/make/{project_key}")
def read_item(project_key: str, summary: str, description: Optional[str] = '-'):
    issue_dict = {
        'project': {
            'key': project_key
        },
        'summary': summary,
        'description': description,
        'issuetype': {
            'name': 'Bug'
        },
    }
    new_issue = jira.create_issue(fields=issue_dict)
    return {"q": summary, "description": description}

@app.get("/status/{issue_id}")
def set_status(issue_id: str, status: Optional[str] = 'To Do'):
    try:
        issue = jira.issue(issue_id)
        transitions = jira.transitions(issue)
        trs = [(t['id'], t['name']) for t in transitions]
        jira.transition_issue(issue, transition=TRANSITION_ID, comment='Тест')
        return {'issue': issue.raw}
    except:
        return Response("Not found", status_code=404)

@app.get("/delete/{issue_id}")
def set_status(issue_id: str, status: Optional[str] = 'To Do'):
    try:
        issue = jira.issue(issue_id)
        issue.delete()
        return {'issue': 'deleted'}
    except:
        return Response("Not found", status_code=404)

@app.post("/tgwh")
async def check_message(request: Request):
    request_body_dict = await request.json()
    update = telebot.types.Update.de_json(request_body_dict)
    bot.process_new_updates([update])
    return ''

@bot.message_handler(commands=['help'])
def send_help(message):
    text = "Вот список команд:\n/done <id> {комментарий} - завершить задачу с комментарием (опционально)"
    text += "\n/projects - список проектов"
    text += "\n/tasks <id> - задачи проекта"
    bot.send_message(chat_id=CHAT_ID, text=text)

@bot.message_handler(commands=['done'])
def close_issue(message):
    params = extract_arg(message.text)
    if len(params) > 0:
        try:
            issue = jira.issue(params[0])
            jira.transition_issue(issue, transition=TRANSITION_ID, comment=(params[1] if len(params) > 1 else "-"))
            bot.send_message(chat_id=CHAT_ID, text="Задача " + params[0] + "помечена как выполненная")
        except:
            bot.send_message(chat_id=CHAT_ID, text="Задача не найдена, попробуйте ещё раз")
    else:
        bot.send_message(chat_id=CHAT_ID, text="Задача не найдена, попробуйте ещё раз")


@bot.message_handler(commands=['test'])
def test_issue(message):
    params = extract_arg(message.text)
    if len(params) > 0:
        try:
            issue = jira.issue(params[0])
            jira.transition_issue(issue, transition=TRANSITION_TEST_ID, comment=(params[1] if len(params) > 1 else "-"))
            bot.send_message(chat_id=CHAT_ID, text="Задача " + params[0] + "помечена как 'на проверку'")
        except:
            bot.send_message(chat_id=CHAT_ID, text="Задача не найдена, попробуйте ещё раз")
    else:
        bot.send_message(chat_id=CHAT_ID, text="Задача не найдена, попробуйте ещё раз")


@bot.message_handler(commands=['projects'])
def load_projects(message):
    text = "Вот список проектов:"
    for project in PROJECTS:
        text += "\n" + project.name + " (" + project.key + ")"

    bot.send_message(chat_id=CHAT_ID, text=text)


@bot.message_handler(commands=['tasks'])
def send_tasks(message):
    params = extract_arg(message.text)
    if len(params) <= 0:
        bot.send_message(chat_id=CHAT_ID, text="Параметры отсутствуют, попробуйте ещё раз")
        return
    try:
        project_key = params[0]
        issues = jira.search_issues(jql_str='project=' + project_key + ' and status not in (Done)', maxResults=100)
        if len(issues) > 0:
            text = 'Вот текущие задачи:'
            for idx, issue in enumerate(issues, start=1):
                url = JIRA_LINK + "/browse/" + issue.key
                name = '<a href="' + url + '">' + issue.fields.summary + " (" + issue.fields.project.name + ", " + issue.key + ")" + "</a>"
                text += "\n" + str(idx) + ". " + name
                if issue.fields.description:
                    description = issue.fields.description if issue.fields.description else "Отсутствует"
                    text += "\nОписание:\n" + re.sub("^\s+|\n|\r|\s+$", '', description)
                text += "\n"
        else:
            text = 'Задачи отсутствуют'
        bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Html", disable_web_page_preview=True)
    except:
        bot.send_message(chat_id=CHAT_ID, text="Проект не найден, попробуйте ещё раз")


@bot.message_handler(func=lambda message: True, content_types=['text'])
def echo_message(message):
    bot.reply_to(message, "Я вас не понимаю")

bot.remove_webhook()

time.sleep(0.2)

bot.set_webhook(url="https://jtg.popstop.space/tgwh")
