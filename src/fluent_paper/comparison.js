/* Source-coordinate PDF sync and paragraph-aligned local Japanese translations. */
(() => {
 'use strict';
 function dimensions(width, comparing=false){
  const outer=48,gap=24,wide=width>=1100;
  let body,left,figure=0;
  if(comparing){
   const usable=width-outer-gap-(wide?gap:0);
   body=Math.min(640,Math.max(120,usable/(wide?2.5:2)));left=body;
   if(wide)figure=Math.min(body/1.6,Math.max(body/2,usable-2*body));
  }else{
   left=wide?176:0;
   const usable=width-outer-(left?gap:0)-(wide?gap:0)-left;
   body=Math.min(640,Math.max(120,usable/(wide?1.5:1)));
   if(wide)figure=Math.min(body/1.6,Math.max(body/2,usable-body));
  }
  return {body,left,figure,leftGap:left?gap:0,rightGap:figure?gap:0,total:outer+left+body+figure+(left?gap:0)+(figure?gap:0),wide};
 }
 window.FluentCompare={dimensions};
 const select=document.getElementById('compare-mode');
 if(!select)return;
 const data=window.FluentComparison||{rows:[],pages:[]};
 const rows=data.rows.map(row=>({...row,node:document.querySelector(`[data-compare-id="${row.id}"]`)})).filter(row=>row.node);
 const savedHeights=new Map(rows.map(row=>[row.node,row.node.style.minHeight]));
 const panel=document.createElement('aside');panel.id='comparison-panel';panel.hidden=true;panel.setAttribute('aria-label','Comparison');
 panel.innerHTML='<div class="comparison-toolbar"><span id="comparison-label"></span><span id="comparison-status" role="status"></span><button id="translate-paper" hidden>Translate</button><button id="close-comparison" aria-label="Close comparison">Close</button></div><div class="comparison-scroll" tabindex="0"><div class="comparison-track"></div></div><div class="translation-credit" hidden>Machine translation · <a href="plamo-license.html" target="_blank">Built with PLaMo</a></div>';
 document.body.append(panel);
 const scroll=panel.querySelector('.comparison-scroll'),track=panel.querySelector('.comparison-track');
 const status=panel.querySelector('#comparison-status'),translate=panel.querySelector('#translate-paper');
 const apiKey=location.pathname.match(/\/papers\/([a-f0-9]{24})\//)?.[1];
 let alignFrame=0;
 let mode='none',frame=0,suppressPanel=0,suppressWindow=0,active=null,pollTimer;
 function layout(){
  const d=dimensions(innerWidth,mode!=='none');
  document.body.classList.add('reader-layout');
  document.body.classList.toggle('reader-comparing',mode!=='none');
  for(const [key,value] of Object.entries(d))if(key!=='wide')document.documentElement.style.setProperty('--reader-'+key.replace(/[A-Z]/g,m=>'-'+m.toLowerCase()),value+'px');
  document.documentElement.style.setProperty('--report-right-margin',d.wide?'1':'0');
  const content=document.getElementById('quarto-content');
  panel.style.left=((content?.getBoundingClientRect().left||0)+24)+'px';
  panel.style.width=d.left+'px';
  window.mechanicsMarginLayout?.invalidate();
 }
 function scheduleAlignment(){
  if(mode==='ja'&&!alignFrame)alignFrame=requestAnimationFrame(()=>{alignFrame=0;align();});
 }
 function resetHeights(){for(const [node,height] of savedHeights)node.style.minHeight=height;}
 function align(){
  if(mode!=='ja')return;
  resetHeights();
  for(const row of rows){
   const cell=track.querySelector(`[data-row="${row.id}"]`);if(!cell)continue;
   const height=Math.max(row.node.getBoundingClientRect().height,cell.getBoundingClientRect().height);
   row.node.style.minHeight=height+'px';
  }
  for(const row of rows){const cell=track.querySelector(`[data-row="${row.id}"]`);if(cell)cell.style.top=(row.node.getBoundingClientRect().top+window.scrollY)+'px';}
  track.style.height=(document.documentElement.scrollHeight+innerHeight)+'px';
  window.mechanicsMarginLayout?.invalidate();syncFromMain();
 }
 function chosenRow(){
  let selected=rows[0];
  for(const row of rows){if(row.node.getBoundingClientRect().top<=120)selected=row;else break;}
  return selected;
 }
 function highlight(page,box){
  track.querySelectorAll('.pdf-highlight').forEach(el=>el.remove());
  const high=document.createElement('div');high.className='pdf-highlight';high.style.cssText=`left:${box[0]*100}%;top:${box[1]*100}%;width:${(box[2]-box[0])*100}%;height:${(box[3]-box[1])*100}%`;page.append(high);
 }
 function syncFromMain(){
  frame=0;if(mode==='none'||performance.now()<suppressWindow)return;
  suppressPanel=performance.now()+100;
  if(mode==='ja'){scroll.scrollTop=window.scrollY+scroll.getBoundingClientRect().top;return;}
  const row=chosenRow();if(!row)return;active=row;
  track.querySelectorAll('.pdf-highlight').forEach(el=>el.remove());
  if(!row.sources.length){scroll.scrollTop=0;return;}
  const rect=row.node.getBoundingClientRect();
  const progress=Math.max(0,Math.min(.999,(120-rect.top)/Math.max(1,rect.height)));
  const index=Math.min(row.sources.length-1,Math.floor(progress*row.sources.length));
  const source=row.sources[index],page=track.querySelector(`[data-page="${source.page}"]`);
  if(!page)return;
  const box=source.bbox||[0,0,1,1];
  highlight(page,box);
  const fraction=progress*row.sources.length-index;
  const y=box[1]+fraction*(box[3]-box[1]);
  scroll.scrollTop=page.offsetTop+y*page.getBoundingClientRect().height-(120-scroll.getBoundingClientRect().top);
  status.textContent=`${source.page} / ${data.pages.length}`;
 }
 function schedule(){if(!frame)frame=requestAnimationFrame(syncFromMain);}
 scroll.addEventListener('wheel',()=>{suppressPanel=0;},{passive:true});
 scroll.addEventListener('keydown',()=>{suppressPanel=0;});
 scroll.addEventListener('scroll',()=>{
  if(mode==='none'||performance.now()<suppressPanel)return;
  suppressWindow=performance.now()+100;
  if(mode==='ja'){window.scrollTo({top:Math.max(0,scroll.scrollTop-scroll.getBoundingClientRect().top),behavior:'instant'});return;}
  const y=scroll.scrollTop+120-scroll.getBoundingClientRect().top;
  const pages=[...track.querySelectorAll('.pdf-page')];
  const page=pages.find(p=>p.offsetTop+p.getBoundingClientRect().height>=y)||pages.at(-1);if(!page)return;
  const relative=(y-page.offsetTop)/Math.max(1,page.getBoundingClientRect().height);
  const preferredX=active?.sources.find(s=>s.page===Number(page.dataset.page))?.bbox?.[0]||0;
  const candidates=rows.flatMap(row=>row.sources.map((source,index)=>({row,source,index}))).filter(x=>x.source.page===Number(page.dataset.page)&&x.source.bbox);
  candidates.sort((a,b)=>{
   const score=x=>Math.max(0,x.source.bbox[1]-relative,relative-x.source.bbox[3])+Math.abs(x.source.bbox[0]-preferredX)*.1;
   return score(a)-score(b);
  });
  const candidate=candidates[0];if(!candidate)return;
  active=candidate.row;const box=candidate.source.bbox;highlight(page,box);
  const within=Math.max(0,Math.min(1,(relative-box[1])/Math.max(.01,box[3]-box[1])));
  const rect=active.node.getBoundingClientRect();
  window.scrollTo({top:Math.max(0,window.scrollY+rect.top+rect.height*(candidate.index+within)/active.sources.length-120),behavior:'instant'});
  status.textContent=`${candidate.source.page} / ${data.pages.length}`;
 },{passive:true});
 async function poll(){
  if(!apiKey||mode!=='ja')return;
  try{
   const response=await fetch(`/api/papers/${apiKey}/translation`);if(!response.ok)return;
   const state=await response.json();
   if(state.status==='ready'&&data.translation_status!=='ready'){location.reload();return;}
   if(['queued','processing'].includes(state.status)){
    status.textContent=state.status==='queued'?'Queued':`Translating ${state.completed||0} / ${state.total||'…'}`;
    translate.disabled=true;pollTimer=setTimeout(poll,3000);
   }else{translate.disabled=false;if(state.status==='failed')status.textContent='Translation failed — retry';}
  }catch{status.textContent='Translation status unavailable';}
 }
 translate.onclick=async()=>{
  translate.disabled=true;status.textContent='Queued';
  try{const response=await fetch(`/api/papers/${apiKey}/translation`,{method:'POST'});if(!response.ok){const error=await response.json();throw Error(error.detail||'Translation failed');}poll();}
  catch(error){status.textContent=error.message;translate.disabled=false;}
 };
 function change(value){
  clearTimeout(pollTimer);resetHeights();mode=value;select.value=value;panel.hidden=value==='none';
  track.replaceChildren();track.style.height='';status.textContent='';
  panel.querySelector('#comparison-label').textContent=value==='pdf'?'Original PDF':'Japanese';
  panel.querySelector('.translation-credit').hidden=value!=='ja';
  translate.hidden=value!=='ja'||!apiKey||data.translation_status==='ready';
  document.body.classList.toggle('comparison-japanese',value==='ja');
  layout();
  if(value==='pdf'){
   data.pages.forEach(([width,height],index)=>{
    const page=document.createElement('div');page.className='pdf-page';page.dataset.page=index+1;page.style.aspectRatio=`${width}/${height}`;
    const img=document.createElement('img');img.src=`pages/${index+1}.jpg`;img.alt=`Original PDF page ${index+1}`;img.loading='lazy';page.append(img);track.append(page);
   });
   schedule();
  }else if(value==='ja'){
   if(data.translation_status!=='ready')status.textContent='Translation not built';
   for(const row of rows){
    const cell=document.createElement('div');cell.className='comparison-row '+row.kind;cell.dataset.row=row.id;
    const font=getComputedStyle(row.node);cell.style.fontSize=font.fontSize;cell.style.lineHeight=font.lineHeight;
    cell.innerHTML=row.translation_html||(row.kind==='equation'?row.html:'');
    track.append(cell);
   }
   align();scheduleAlignment();
   const math=window.MathJax;
   if(math?.typesetPromise)math.typesetPromise([track]).then(align);
   else math?.startup?.promise?.then(()=>math.typesetPromise([track]).then(align));
   poll();
  }
  const url=new URL(location.href);if(value==='none')url.searchParams.delete('compare');else url.searchParams.set('compare',value);history.replaceState(null,'',url);
 }
 select.addEventListener('change',()=>change(select.value));
 panel.querySelector('#close-comparison').onclick=()=>{change('none');select.focus();};
 window.addEventListener('scroll',schedule,{passive:true});
 window.addEventListener('resize',()=>{layout();if(mode==='ja')scheduleAlignment();else schedule();});
 document.fonts?.ready.then(()=>{layout();scheduleAlignment();});
 document.fonts?.addEventListener('loadingdone',scheduleAlignment);
 window.addEventListener('load',()=>{
  const settled=()=>{layout();scheduleAlignment();schedule();};
  if(window.MathJax?.startup?.promise)window.MathJax.startup.promise.then(settled);else settled();
 });
 // Margin items leave normal flow after their first measurement; image/math
 // completion can also move paragraphs. Reconcile after those layout changes.
 if(window.ResizeObserver){
  const resize=new ResizeObserver(()=>{scheduleAlignment();schedule();});
  const main=document.querySelector('main');if(main)resize.observe(main);
  window.addEventListener('pagehide',()=>resize.disconnect(),{once:true});
 }
 const initial=new URL(location.href).searchParams.get('compare');change(['pdf','ja'].includes(initial)?initial:'none');
 window.FluentCompare.setMode=change;
})();
