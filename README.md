Changed GUI from a runner clone to a web UI, now it uses the runner.py file directly and opens at (http://localhost:5000/)  

# please make improve GUI from here  
Capstone_AI/     
├── config_parser.py  
├── runner.py  
├── core/  
│   ├── advanced_analytics.py  
│   ├── certainty_factors.py  
│   ├── config_manager.py  
│   ├── inference_engine.py  
│   ├── knowledge_base.py  
│   └── rule_miner.py  
├── detection/  
│   ├── eigrp_tree.py  
│   ├── interface_tree.py  
│   ├── ospf_tree.py  
│   └── problem_detector.py  
├── history/  
│   ├── configs/  
│   ├── knowledge/  
│   └── runs/  
├── resolution/  
│   ├── fix_applier.py  
│   └── fix_recommender.py  
├── utils/  
│   ├── network_utils.py  
│   ├── reporter.py  
│   └── telnet_utils.py  
└── web_gui/                 # ← NEW: Flask web interface  
    ├── app.py               # Flask application entry point  
    ├── requirements.txt     # Python dependencies for web_gui  
    ├── static/              # Static assets served to browser  
    │   ├── app.js           # Frontend JavaScript logic  
    │   ├── style.css        # Stylesheet for the UI  
    │   └── images/          # Image assets (e.g., current_gui.png)  
    └── templates/           # Jinja2 HTML templates  
        └── index.html       # Main page template  


![GUI Screenshot](https://raw.githubusercontent.com/darienrh/CAPSTONE/GUI/current_gui.png)


# To Do:  
- change discovered routers text to different color (need to select them to see router numbers)
- add more pages for things like network statistics, topology view, IDS view, etc

# Run it:
user1@ubuntu:~/Capstone_AI/web_gui$ python3 -m venv venv  
source venv/bin/activate  
pip install -r requirements.txt  
python3 app.py  


 

