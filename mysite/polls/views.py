from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.

def index(request):
    return HttpResponse("Welcome to my site!")

def detail(request, question_id):
    return HttpResponse(f'u r looking at questions#{question_id}')

def result(request, question_id):
    return HttpResponse(f'u r looking at results of questions#{question_id}')

def vote(request, question_id):
    return HttpResponse(f'u r voting on questions#{question_id}')