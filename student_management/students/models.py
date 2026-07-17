from django.db import models

class Student(models.Model):
    name = models.CharField(max_length=100)
    
    age = models.IntegerField()
    
    email = models.EmailField()
    
    course = models.CharField(max_length=50, default="Python")
    
    registration_date = models.DateTimeField(auto_now_add=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} — {self.course}"

    def is_adult(self):
        return self.age >= 18