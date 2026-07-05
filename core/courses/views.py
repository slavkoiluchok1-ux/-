from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth.models import User
from .models import StudentProfile, CourseSelection
from .forms import StudentRegistrationForm, CourseSelectionFormSet

def register_view(request):
    if request.method == 'POST':
        user_form = StudentRegistrationForm(request.POST)
        formset = CourseSelectionFormSet(request.POST)
        if user_form.is_valid() and formset.is_valid():
            with transaction.atomic():
                data = user_form.cleaned_data
                user = User.objects.create_user(
                    username=data['username'],
                    email=data['email'],
                    password=data['password1'],
                    first_name=data['first_name'],
                    last_name=data['last_name']
                )
                profile = StudentProfile.objects.create(
                    user=user,
                    age=data['age'],
                    phone=data['phone']
                )
                for form in formset:
                    if form.cleaned_data:
                        CourseSelection.objects.create(
                            student=profile,
                            course=form.cleaned_data['course'],
                            priority=form.cleaned_data['priority']
                        )
            login(request, user)
            return redirect('dashboard')
    else:
        user_form = StudentRegistrationForm()
        formset = CourseSelectionFormSet()
    return render(request, 'courses/register.html', {'user_form': user_form, 'formset': formset})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'courses/login.html', {'form': form})

def logout_view(request):
    if request.method == 'POST' or request.method == 'GET':
        logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    selections = CourseSelection.objects.filter(student__user=request.user).order_by('priority')
    return render(request, 'courses/dashboard.html', {'selections': selections})

@login_required
def profile_view(request):
    profile = request.user.profile
    return render(request, 'courses/profile.html', {'profile': profile})