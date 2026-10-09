// Import helpers from a task-owned .mjs module; use the bundled artifact-tool runtime.
// This is a blank scientific canvas, not a prescribed narrative or slide count.
import { Presentation } from '@oai/artifact-tool';
export const pt = value => value * 4 / 3;
export const fonts = Object.freeze({ chinese: 'SimHei', latin: 'Arial', math: 'Times New Roman' });
export function mixedText(text, size=24) {
  return String(text).split('\n').map(line => ({runs:(line.match(/[^\x00-\x7F]+|[\x00-\x7F]+/g)||['']).map(run=>({run,
    textStyle:{typeface:/^[\x00-\x7F]+$/.test(run)?fonts.latin:fonts.chinese,fontSize:`${size}pt`,color:'#000000'}}))}));
}
export function createDeck() {
  return Presentation.create({ slideSize: { width: 1280, height: 720 } });
}
export function addText(slide, text, box, role='body', family=fonts.chinese) {
  const size=role==='title'?32:role==='footer'?16:24;
  const shape = slide.shapes.add({ geometry:'textbox', name:role, position:box,
    fill:'none', line:{fill:'none',width:0} });
  shape.text.style = { typeface:family, fontSize:pt(size),
    color:'#000000', autoFit:'none', verticalAlignment:'middle' };
  shape.text = family===fonts.chinese ? mixedText(text,size) : String(text).split('\n').map(run=>({runs:[{run,textStyle:{typeface:family,fontSize:`${size}pt`,color:'#000000'}}]}));
  return shape;
}
export function addScientificSlide(deck, title, number) {
  const slide=deck.slides.add(); slide.background.fill='#FFFFFF';
  addText(slide,title,{left:56,top:28,width:1168,height:62},'title');
  if(number!==undefined) addText(slide,String(number),{left:1172,top:672,width:52,height:30},'footer',fonts.latin);
  return slide;
}
