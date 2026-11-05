export function contextSignature(context){
 const p=context.profile;const peer=context.comparePair?.find(item=>item.id!==context.selectedId&&item.category===p.category);
 const weights=Object.entries(p.weights||{}).sort(([a],[b])=>a.localeCompare(b));
 return JSON.stringify([p.category,p.subcategory||null,p.curated_only===true,Number(p.budget),p.scenario,p.needs,weights,p.include_used===true,p.include_reference!==false,context.selectedId||null,peer?.id||null]);
}

export function applyAdvisorTurn(context,pool,turn,captured){
 if(turn.version!==2||contextSignature(context)!==captured)return false;
 if(turn.profile_update){Object.assign(context.profile,turn.profile_update);context.reportDocument=null;context.pendingPrice=[];context.overBudget=[];context.process=null}
 const map=new Map([...pool,...context.products].filter(p=>p.category===turn.context_snapshot.category).map(p=>[p.id,p]));
 for(const p of turn.products)map.set(p.id,{...(map.get(p.id)||{}),...p});
 context.products=[...map.values()];
 const ids=turn.context_update?.pair_ids||[];context.comparePair=ids.map(id=>map.get(id)).filter(Boolean);
 if(turn.context_update?.selected_id&&map.has(turn.context_update.selected_id))context.selectedId=turn.context_update.selected_id;
 context.assistantState=turn.state;context.assistantSuggestions=turn.suggestions;context.assistantScope=contextSignature(context);
 return true;
}

export function prepareNavigation(context,action,products){
 if(!['compare','report'].includes(action.type)||!products.length||products.some(p=>p.category!==context.profile.category))throw new Error('请按当前品类重新核对这些产品');
 if(new Set(products.map(p=>p.id)).size!==products.length)throw new Error('请选择不同产品');
 context.comparePair=products;context.products=products;context.selectedId=products[0].id;
 if(action.type==='report')context.reportDocument=null;
 return {tab:action.type==='report'?'report':'compare',product:products[0]};
}

export function restoredPairIds(pool,seed,remembered){
 if(!Array.isArray(remembered)||remembered.length!==2)return null;
 const ids=remembered.map(p=>p.id);
 if(ids[0]===ids[1]||ids.some(id=>!pool.some(p=>p.id===id))||seed&&!ids.includes(seed))return null;
 return seed?[seed,ids.find(id=>id!==seed)]:ids;
}
