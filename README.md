UPDATE: Friday April 3 (today), most of the code in the vm should be fine, but replace runner.py and telnet_utils.py 



All AI features implemented, still some bugs and optimizations needed. 

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
└── web_gui/                 
