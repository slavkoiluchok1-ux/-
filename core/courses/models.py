
from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    age = models.IntegerField()
    phone = models.CharField(max_length=13)

    def __str__(self):
        return self.user.username

class CourseSelection(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='selections')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    priority = models.IntegerField()

    class Meta:
        unique_together = (
            ('student', 'course'),
            ('student', 'priority'),
        )

    def __str__(self):
        return f"{self.student.user.username} - {self.course.title} ({self.priority})"