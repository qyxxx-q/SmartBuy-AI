"""Real-catalog local-mode conversation examples; no external model or audio calls."""
import json
from unittest.mock import patch
from pathlib import Path
from app import app
from assistant import public_config
root=Path(__file__).resolve().parent
profile=dict(category='手机',budget=2000,scenario='老人使用',needs='2000元手机，给父母用，希望字体大、操作简单、续航好。',weights=dict(performance=2,price=30,battery=25,portability=8,ease=25,camera=0,screen=10),include_reference=True,include_used=False)
client=app.test_client();state={};focus=None;peer=None;examples=[];initial_profile=profile.copy()
with patch('assistant.call_llm',return_value=None):
    for question,confirmation in [('按当前预算推荐几款',None),('另一款呢',None),('它和另一款有什么区别？',None),('预算改成3000元，给父母用',None),('确认调整预算','apply')]:
        payload=dict(question=question,profile=profile,state=state,product_id=focus,compare_id=peer)
        if confirmation:payload['confirmation']=confirmation
        response=client.post('/api/chat',json=payload);assert response.status_code==200
        result=response.get_json();assert result['mode']=='local'
        for p in result['products']:
            if p['role']=='candidate':assert p['recommendation_eligible'] and p['price']<=result['context_snapshot']['budget']
        if result['intent']=='confirm':assert profile['budget']==2000 and result['profile_update'] is None
        examples.append(dict(question=question,input_profile=profile.copy(),result=result))
        if result['profile_update']:profile=result['profile_update']
        state=result['state'];focus=state['focus_id'];peer=next((i for i in state['pair_ids'] if i!=focus),None)
assert profile['budget']==3000
pool=client.post('/api/recommend',json=dict(initial_profile,purpose='compare')).get_json()['products']
output=dict(profile=initial_profile,pool=pool,examples=examples,model_configured=public_config()['configured'])
(root/'data'/'assistant_examples.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(turns=len(examples),first_candidates=[dict(id=p['id'],name=p['name'],price=p['price']) for p in examples[0]['result']['products']],comparison=examples[2]['result']['state']['pair_ids'],confirmed_budget=profile['budget'],model_configured=output['model_configured']),ensure_ascii=True))
