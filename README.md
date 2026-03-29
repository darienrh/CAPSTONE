Changed GUI from a runner clone to a web UI, now it uses the runner.py file directly and opens at (http://localhost:5000/)  

# please improve GUI from here  

# To Do:  
- improve design and styles   
- finish topology page (currently broken)  
- add more pages for things like network statistics, topology view, IDS view, etc  

# Run it:
Option 1 venv:  
user1@ubuntu:~/Capstone_AI/web_gui$ python3 -m venv venv  
source venv/bin/activate  
pip install -r requirements.txt  
python3 app.py  

Option 2 vm:  
cd web_gui  
python3 app.py     

# View 
1. inside VM at http://localhost:5000  
2. Or view on PC at http://<vm's ip>:5000  

# Pictures: 
- i added light/dark toggle bar
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/gui_03_29.png)
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/gui2_03_29.png)
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/gui3_03_29.png)
