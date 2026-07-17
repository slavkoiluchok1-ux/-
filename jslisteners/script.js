const btn = document.getElementById("launch")


btn.addEventListener("click",() =>{
    btn.textContentm = "запуск підтверджено"
    btn.style.backgroundColor = "#e74c3c"
    btn.style.color = "#fff"
    btn.style.border = " 2 px solid #e74c3c"
})

setTimeout(() =>{
    console.log("це повідомлення з'явиться через 3 секунди")
},3000)