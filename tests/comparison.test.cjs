const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.JSDOM_MODULE||'jsdom');
const source=fs.readFileSync('src/fluent_paper/comparison.js','utf8');
const dom=new JSDOM('<div id="quarto-content"><select id="compare-mode"><option value="none">Off</option><option value="pdf">PDF</option><option value="ja">Japanese</option></select><main><p data-compare-id="a">Original</p><p data-compare-id="b">Next</p></main></div>',{runScripts:'outside-only',pretendToBeVisual:true,url:'https://example.test/sample/'});
const w=dom.window;let now=1000,translatedHeight=120;const resizeCallbacks=[];w.ResizeObserver=class{constructor(cb){resizeCallbacks.push(cb)}observe(){}disconnect(){}};w.performance.now=()=>now;
w.scrollTo=({top})=>{w.scrollY=top;w.dispatchEvent(new w.Event('scroll'))};
w.FluentComparison={translation_status:'ready',pages:[[600,800]],rows:[{id:'a',kind:'paragraph',sources:[{page:1,bbox:[.1,.1,.9,.3]}],html:'<p>Original</p>',translation_html:'<p>日本語の段落</p>'},{id:'b',kind:'paragraph',sources:[{page:1,bbox:[.1,.4,.9,.6]}],html:'<p>Next</p>',translation_html:'<p>次の段落</p>'}]};
const originalRect=w.HTMLElement.prototype.getBoundingClientRect;
w.HTMLElement.prototype.getBoundingClientRect=function(){
 const first=w.document.querySelector('[data-compare-id="a"]');
 const base=this.dataset.compareId==='a'?200:this.dataset.compareId==='b'?200+(parseFloat(first.style.minHeight)||60)+20:0;
 if(this.dataset.compareId)return {top:base-w.scrollY,height:parseFloat(this.style.minHeight)||60,left:400};
 if(this.classList.contains('comparison-row'))return {top:0,height:translatedHeight};
 if(this.classList.contains('pdf-page'))return {top:0,height:800};
 if(this.classList.contains('comparison-scroll'))return {top:50,height:700};
 return originalRect.call(this);
};
w.eval(source);
for(const width of [800,1100,1440,1800,2560])for(const comparing of [false,true]){
 const d=w.FluentCompare.dimensions(width,comparing);assert(d.body<=640);assert(d.total<=width+.01);
 if(comparing)assert.equal(d.left,d.body);
 if(d.wide){assert(d.figure>=d.body/2-.01);assert(d.figure<=d.body/1.6+.01);}
}
(async()=>{
w.FluentCompare.setMode('ja');
assert(w.document.body.classList.contains('reader-comparing'));
const first=w.document.querySelector('[data-compare-id="a"]'),second=w.document.querySelector('[data-compare-id="b"]');
assert.equal(first.style.minHeight,'120px');assert.equal(second.style.minHeight,'120px');
assert.equal(w.document.querySelector('[data-row="a"]').style.top,'200px');assert.equal(w.document.querySelector('[data-row="b"]').style.top,'340px');
translatedHeight=160;resizeCallbacks.forEach(cb=>cb());await new Promise(resolve=>setTimeout(resolve,30));assert.equal(first.style.minHeight,'160px');assert.equal(w.document.querySelector('[data-row="b"]').style.top,'380px');
const scroll=w.document.querySelector('.comparison-scroll');now+=200;scroll.scrollTop=350;scroll.dispatchEvent(new w.Event('scroll'));assert.equal(w.scrollY,300);
w.FluentCompare.setMode('pdf');assert.equal(first.style.minHeight,'');assert.equal(w.document.querySelectorAll('.pdf-page').length,1);assert.equal(w.document.querySelector('.pdf-page img').getAttribute('src'),'pages/1.jpg');
now+=200;scroll.scrollTop=100;scroll.dispatchEvent(new w.Event('scroll'));assert.equal(w.scrollY,113.75);assert(w.document.querySelector('.pdf-highlight'));now+=200;w.dispatchEvent(new w.Event('scroll'));await new Promise(resolve=>setTimeout(resolve,30));assert(Math.abs(scroll.scrollTop-100)<.01);
w.FluentCompare.setMode('none');assert(!w.document.body.classList.contains('reader-comparing'));assert(w.document.getElementById('comparison-panel').hidden);
w.close();console.log('Comparison: responsive ratios, paragraph alignment, reverse scroll and mode restoration passed');

})().catch(error=>{console.error(error);w.close();process.exitCode=1});
