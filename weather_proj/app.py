from flask import Flask, jsonify, render_template, request
import requests

from models import Session, User
from config import OPENWEATHER_API_KEY

app = Flask(__name__)