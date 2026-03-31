Changed GUI from a runner clone to a web UI, now it uses the runner.py file directly and opens at (http://localhost:5000/)  

# please improve GUI from here  

# To Do:  
- improve design and styles    
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
- fixed topology page, now the topology is a link where you can view and manage the topology in web. 
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/gui-03-31-01.png)
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/gui-03-31-02.png)
![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/top1.png)
