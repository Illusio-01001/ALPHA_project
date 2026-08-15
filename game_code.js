"use strict";
/* ==========================================================================
   ALPHA PROJECT - HTML/WebGL port of alpha_project.py
   All gameplay data (buildings/items/recipes) is exported verbatim from the
   Python source into D, so the simulation stays in sync with the original.
   ========================================================================== */
const C = D.consts, CELL = C.CELL, GR = D.GRID_RANGE || C.GRID_RANGE;
const S = a => new Set(a);
const CONVEYOR_LIKE = S(D.CONVEYOR_LIKE), PIPE_LIKE = S(D.PIPE_LIKE),
      PIPE_CONNECTABLE = S(D.PIPE_CONNECTABLE), CROSSROAD = S(D.CROSSROAD_TYPES),
      LIQUID = S(D.LIQUID_ITEMS), FUEL_LIKE = S(D.FUEL_LIKE_ITEMS),
      POWER_NODES = S(D.POWER_NODE_TYPES), DRONE_UI = S(D.DRONE_UI_TYPES);
const FAMILY = {
  gas_turbine:[S(D.GAS_TURBINE_FAMILY), D.GAS_TURBINE_PART_BONUS],
  coal_power_plant:[S(D.COAL_PLANT_FAMILY), D.COAL_PLANT_PART_BONUS],
  modular_turbine:[S(D.MODULAR_TURBINE_FAMILY), D.MODULAR_TURBINE_PART_BONUS],
};
const DIRS = {N:[0,-1], S:[0,1], E:[1,0], W:[-1,0]};
const DIRLIST = [[1,0],[0,-1],[-1,0],[0,1]];   // E N W S  (rotation order)
const key = (x,z) => x + "," + z;
const lab = t => D.ITEM_LABEL[t] || t;
const has = (o,k) => Object.prototype.hasOwnProperty.call(o,k);

/* ===================== math ===================== */
function m4id(){return new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);}
function m4mul(a,b){const o=new Float32Array(16);
  for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;
    for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k]; o[i*4+j]=s;} return o;}
function m4persp(fov,asp,n,f){const t=1/Math.tan(fov*Math.PI/360),o=new Float32Array(16);
  o[0]=t/asp;o[5]=t;o[10]=(f+n)/(n-f);o[11]=-1;o[14]=2*f*n/(n-f);return o;}
function m4look(ex,ey,ez,cx,cy,cz){
  let zx=ex-cx,zy=ey-cy,zz=ez-cz;let l=Math.hypot(zx,zy,zz)||1;zx/=l;zy/=l;zz/=l;
  let xx=zz*0-1*zy,xy=zx*0-0*zz,xz=0*zy-zx*0; // up=(0,1,0) cross
  xx=1*zz-0*zy; xy=0*zx-0*zz; xz=0*zy-1*zx;
  l=Math.hypot(xx,xy,xz)||1;xx/=l;xy/=l;xz/=l;
  const yx=zy*xz-zz*xy, yy=zz*xx-zx*xz, yz=zx*xy-zy*xx;
  return new Float32Array([xx,yx,zx,0, xy,yy,zy,0, xz,yz,zz,0,
    -(xx*ex+xy*ey+xz*ez), -(yx*ex+yy*ey+yz*ez), -(zx*ex+zy*ey+zz*ez), 1]);
}

/* ===================== GL ===================== */
const cv = document.getElementById("gl");
const gl = cv.getContext("webgl", {antialias:true, alpha:false});
const VS = `attribute vec3 aP;attribute vec3 aC;uniform mat4 uVP;uniform vec3 uCam;
varying vec3 vC;varying float vD;
void main(){gl_Position=uVP*vec4(aP,1.0);vC=aC;vD=length(aP-uCam);}`;
const FS = `precision mediump float;varying vec3 vC;varying float vD;
uniform vec3 uFog;uniform float uDen;
void main(){float f=clamp(exp(-pow(vD*uDen,2.0)),0.0,1.0);
gl_FragColor=vec4(mix(uFog,vC,f),1.0);}`;
function sh(t,src){const s=gl.createShader(t);gl.shaderSource(s,src);gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(s);return s;}
const prog = gl.createProgram();
gl.attachShader(prog,sh(gl.VERTEX_SHADER,VS));gl.attachShader(prog,sh(gl.FRAGMENT_SHADER,FS));
gl.linkProgram(prog);gl.useProgram(prog);
const aP=gl.getAttribLocation(prog,"aP"), aC=gl.getAttribLocation(prog,"aC"),
      uVP=gl.getUniformLocation(prog,"uVP"), uFog=gl.getUniformLocation(prog,"uFog"),
      uDen=gl.getUniformLocation(prog,"uDen"), uCam=gl.getUniformLocation(prog,"uCam");
gl.enableVertexAttribArray(aP);gl.enableVertexAttribArray(aC);
gl.enable(gl.DEPTH_TEST);

/* dynamic vertex stream (pos3 + col3) */
const MAXV = 900000;
const VB = new Float32Array(MAXV*6); let vn = 0;
const buf = gl.createBuffer();
function reset(){vn=0;}
function vtx(x,y,z,r,g,b){if(vn>=MAXV)return;const i=vn*6;
  VB[i]=x;VB[i+1]=y;VB[i+2]=z;VB[i+3]=r;VB[i+4]=g;VB[i+5]=b;vn++;}
function flush(mode){
  if(!vn)return;
  gl.bindBuffer(gl.ARRAY_BUFFER,buf);
  gl.bufferData(gl.ARRAY_BUFFER,VB.subarray(0,vn*6),gl.DYNAMIC_DRAW);
  gl.vertexAttribPointer(aP,3,gl.FLOAT,false,24,0);
  gl.vertexAttribPointer(aC,3,gl.FLOAT,false,24,12);
  gl.drawArrays(mode,0,vn); vn=0;
}

/* ---- transform stack (mimics glPushMatrix/glTranslate/glRotate) ---- */
let TX=0,TY=0,TZ=0,TA=0;   // translate + Y rotation (degrees)
function tp(x,y,z){ // apply current transform to a local point
  if(TA){const r=TA*Math.PI/180,c=Math.cos(r),s=Math.sin(r);
    return [TX+x*c+z*s, TY+y, TZ-x*s+z*c];}
  return [TX+x,TY+y,TZ+z];
}
const shade=(c,f)=>[Math.min(c[0]*f,1),Math.min(c[1]*f,1),Math.min(c[2]*f,1)];

function cube(cx,cy,cz,sx,sy,sz,col){
  const t=shade(col,1.25), s=shade(col,.75), b=shade(col,.5);
  const x0=cx-sx/2,x1=cx+sx/2,y0=cy-sy/2,y1=cy+sy/2,z0=cz-sz/2,z1=cz+sz/2;
  const P=[[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1],
           [x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]].map(p=>tp(p[0],p[1],p[2]));
  const q=(a,b_,c,d,co)=>{vtx(...P[a],...co);vtx(...P[b_],...co);vtx(...P[c],...co);
                          vtx(...P[a],...co);vtx(...P[c],...co);vtx(...P[d],...co);};
  q(4,5,6,7,t); q(3,2,1,0,b); q(3,2,6,7,s); q(1,0,4,5,s); q(0,3,7,4,s); q(2,1,5,6,s);
}
function cyl(cx,y0,cz,r,h,col,sides){
  sides=sides||8; const t=shade(col,1.2), s=shade(col,.75), b=shade(col,.5);
  const T=[],B=[];
  for(let i=0;i<sides;i++){const a=2*Math.PI*i/sides,dx=r*Math.cos(a),dz=r*Math.sin(a);
    T.push(tp(cx+dx,y0+h,cz+dz)); B.push(tp(cx+dx,y0,cz+dz));}
  const ct=tp(cx,y0+h,cz), cb=tp(cx,y0,cz);
  for(let i=0;i<sides;i++){const j=(i+1)%sides;
    vtx(...B[i],...s);vtx(...B[j],...s);vtx(...T[j],...s);
    vtx(...B[i],...s);vtx(...T[j],...s);vtx(...T[i],...s);
    vtx(...ct,...t);vtx(...T[i],...t);vtx(...T[j],...t);
    vtx(...cb,...b);vtx(...B[j],...b);vtx(...B[i],...b);}
}
function pyr(cx,y0,cz,base,h,col){
  const t=shade(col,1.2), s=shade(col,.8), hs=base/2;
  const ap=tp(cx,y0+h,cz);
  const K=[[cx-hs,y0,cz-hs],[cx+hs,y0,cz-hs],[cx+hs,y0,cz+hs],[cx-hs,y0,cz+hs]].map(p=>tp(...p));
  for(let i=0;i<4;i++){const co=i%2?s:t;
    vtx(...ap,...co);vtx(...K[i],...co);vtx(...K[(i+1)%4],...co);}
}

/* ===================== building models ===================== */
/* Archetype-based: each building gets a silhouette from its role, with the
   distinctive ones (drills, turbines, towers) hand-shaped like the original. */
const BC = t => D.BUILD_COLOR[t] || [.6,.6,.6];
const MINERS = S(["coal_miner","copper_miner","iron_miner","lead_miner","sand_miner","wood_cutter"]);
const TANKS = S(["refinery","chem_plant","boiler","scrubber","water_treatment","condenser",
  "gas_refiner","oil_classifier","diesel_refiner","filter","fragment_processor","ore_refiner",
  "heavy_oil_separator","oxidation_chamber","chemical_reactor","steam_cracker","plastic_refinery",
  "air_separator","molder"]);
const BOXES = S(["furnace","press","alloy_furnace","circuit_assembler","assembly_plant",
  "battery_plant","silicon_refiner","lathe","battery_cell","hv_battery","electrolyzer",
  "transformer","research","power_meter"]);

function model(t,wx,wz,ang,at,active,gauge,connects,fcol){
  TX=wx;TY=0;TZ=wz;TA=ang;
  const c=BC(t), dark=shade(c,.55), lite=shade(c,1.25);
  const A=active?1:0;
  const belt=()=>{cube(0,.12,0,CELL*.9,.24,CELL*.9,c);
    cube(0,.22,-CELL*.4,CELL*.9,.1,.08,dark);cube(0,.22,CELL*.4,CELL*.9,.1,.08,dark);
    for(let i=0;i<3;i++){const p=((at*1.4+i/3)%1)-.5;
      cube(p*CELL*.85,.26,0,.08,.05,CELL*.7,shade(c,.35));}};

  if(CONVEYOR_LIKE.has(t)&&t!=="wire"&&t!=="drone_payload"){belt();
    if(t==="conveyor_3way")cube(0,.12,CELL*.5,CELL*.4,.24,CELL*.9,c);
    if(t==="conveyor_4way"){cube(0,.12,-CELL*.5,CELL*.4,.24,CELL*.9,c);cube(0,.12,CELL*.5,CELL*.4,.24,CELL*.9,c);}
    return;}
  if(t==="item_filter"){belt();
    const g=fcol||[.75,.75,.78], p=A?(.85+.15*Math.abs(Math.sin(at*3))):1;
    cube(0,.5,0,.1,.55*p,CELL*.85,g);return;}
  if(t==="wire"){cube(-CELL*.35,.3,0,.1,.6,.1,[.1,.1,.11]);
    cube(CELL*.35,.3,0,.1,.6,.1,[.1,.1,.11]);cube(0,.55,0,CELL*.85,.05,.05,c);return;}
  if(PIPE_LIKE.has(t)){cyl(0,.1,0,.28,.3,c,10);cyl(0,.38,0,.34,.06,shade(c,.7),10);
    if(t==="pipe"&&connects){TA=0;for(const[dx,dz]of connects)
      cube(dx*CELL*.35,.1,dz*CELL*.35,dx?CELL*.5:.3,.2,dz?CELL*.5:.3,c);TA=ang;}
    if(t==="pipe_3way")cube(0,.1,CELL*.4,.2,.2,CELL*.55,c);
    if(t==="pipe_4way")cube(0,.1,0,CELL*.9,.2,.2,c);return;}
  if(CROSSROAD.has(t)){
    if(t==="conveyor_crossroad"){cube(0,.12,0,CELL*.95,.2,.28,c);cube(0,.12,0,.28,.2,CELL*.95,c);
      cube(0,.24,0,.3,.06,.3,[.9,.65,.15]);}
    else if(t==="pipe_crossroad"){cyl(0,.1,0,.24,.3,c,10);cube(0,.14,0,CELL*.9,.16,.16,c);
      cube(0,.14,0,.16,.16,CELL*.9,c);}
    else{cube(0,.1,0,CELL*.9,.2,.3,[.55,.55,.58]);cube(0,.16,0,.3,.2,CELL*.9,[.3,.55,.55]);
      cyl(0,.3,0,.2,.1,c,8);}return;}

  if(MINERS.has(t)){const b=A?Math.sin(at*5)*.14:0;
    cube(0,.55,0,CELL*.75,.9,CELL*.75,c);cyl(0,1+b,0,.16,.5,[.3,.3,.32]);
    pyr(0,.12+b,0,.45,-.55,[.25,.22,.2]);return;}
  if(t==="oil_pump"||t==="water_pump"||t==="gas_extractor"){
    const s=A?Math.sin(at*2.2)*.28:0;
    cube(0,.3,0,CELL*.8,.6,CELL*.7,c);cube(-.3,.95,0,.16,.9,.16,shade(c,.7));
    cube(.15,1.35+s,0,1.3,.14,.16,lite);cube(.72,1.05+s*1.6,0,.16,.5,.16,dark);return;}
  if(t==="mineshaft_drill"){
    const lv=gauge||1, hc=fcol||[.35,.35,.38];
    cube(0,.15,0,CELL*.95,.3,CELL*.95,c);
    for(const[dx,dz]of[[.6,.6],[-.6,.6],[.6,-.6],[-.6,-.6]])cube(dx,1.1,dz,.12,2,.12,shade(c,.7));
    cube(0,2.05,0,CELL*.7,.16,CELL*.7,shade(c,.7));
    const sl=.6+lv*.35, sp=(A&&fcol)?at*260:0, sa=TA; TA=ang+sp;
    cyl(0,.3-sl,0,.13,sl,hc,6); pyr(0,.3-sl,0,.3,-.35,hc); TA=sa; return;}

  if(t==="solar"){cube(0,.35,0,.14,.7,.14,[.3,.3,.32]);cube(0,.78,0,CELL*.85,.08,CELL*.6,c);return;}
  if(t==="depot"){cube(0,.85,0,CELL*.9,1.5,CELL*.9,c);pyr(0,1.6,0,CELL,.6,shade(c,.7));
    cube(CELL*.55,.3,0,.35,.55,CELL*.55,shade(c,.8));return;}
  if(t==="coal_gen"||t==="oil_gen"||t==="diesel_gen"||t==="thermal_plant"){
    cube(0,.85,0,CELL*.85,1.7,CELL*.85,c);
    cyl(-.35,1.7,-.3,.18,1,[.15,.15,.16]);cyl(.35,1.7,-.3,.18,.75,[.15,.15,.16]);
    if(A){const g=.5+.5*Math.abs(Math.sin(at*3));cube(0,.4,CELL*.4,.4,.3,.12,[g,g*.4,.08]);}return;}
  if(t==="coal_power_plant"){cube(0,1.05,0,CELL*.95,2.1,CELL*.95,c);
    cyl(-.45,2.1,-.15,.24,1.7,[.16,.12,.1]);cyl(.45,2.1,-.15,.24,1.4,[.16,.12,.1]);
    const g=A?(.55+.35*Math.abs(Math.sin(at*2.5))):.15;
    cube(0,.5,CELL*.45,.5,.4,.14,[g,g*.35,g*.08]);
    cyl(0,0,-CELL*.45,.3,1.5,[.35,.55,.75]);return;}
  if(t==="turbine"||t==="gas_turbine"||t==="modular_turbine"){
    const big=t!=="turbine";
    if(big)cube(0,.5,0,CELL*.8,1,CELL*.8,c); else cyl(0,0,0,.38,.9,c);
    cyl(0,big?1:.9,0,.15,.35,[.4,.4,.42]);
    const sa=TA;TA=ang+(A?at*250:0);
    cube(0,big?1.35:1.2,0,.72,.07,.09,lite);cube(0,big?1.35:1.2,0,.09,.07,.72,lite);TA=sa;return;}
  if(t==="turbine_hp_stage"||t==="turbine_ip_stage"||t==="turbine_lp_stage"||t==="turbine_crankshaft_block"){
    cube(0,.5,0,CELL*.7,.9,CELL*.32,[.4,.4,.42]);
    const sa=TA;TA=ang+(A?at*300:0);cyl(0,.35,0,.12,.3,lite,6);TA=sa;return;}
  if(t==="firebox"||t==="blast_furnace"||t==="furnace"){
    const g=A?(.55+.45*Math.abs(Math.sin(at*2.5))):.2;
    const big=t==="blast_furnace";
    cube(0,big?.7:.6,0,CELL*(big?.85:.8),big?1.4:1.2,CELL*(big?.85:.8),c);
    cyl(.35,big?1.4:1.2,-.2,.2,.9,[.32,.29,.27]);
    cube(0,.5,CELL*.4,.5,.4,.14,[g,g*.45,g*.1]);return;}
  if(t==="exhaust_stack"){cube(0,.14,0,CELL*.6,.28,CELL*.6,[.3,.28,.26]);
    cyl(0,.3,0,.32,2,c);if(A){const p=.1+.05*Math.abs(Math.sin(at*1.5));
      cube(0,2.35,0,p,p,p,[.6,.6,.62]);}return;}
  if(t==="heat_exchanger"){cube(0,.5,0,CELL*.8,1,CELL*.55,c);
    const g=A?(.5+.5*Math.abs(Math.sin(at*3))):.2;
    for(const i of[-1,0,1])cyl(i*.3,.5,CELL*.3,.08,1,[.85*g,.45*g,.2*g],8);return;}
  if(t==="coal_feeder"){cube(0,.14,0,CELL*.7,.28,CELL*.7,c);pyr(0,.7,0,.5,-.55,shade(c,.6));
    cube(0,.86+(A?Math.sin(at*4)*.05:0),0,.16,.12,.16,[.1,.09,.08]);return;}
  if(t==="data_power_node"||t==="turbine_controller_block"||t==="gas_input_block"){
    cube(0,.35,0,CELL*.55,.7,CELL*.55,c);cyl(0,.7,0,.06,.5,[.3,.3,.32]);
    const lv=t==="data_power_node"?(gauge||2):1, on=A?(Math.floor(at*2.5)%2===0):true;
    for(let i=0;i<3;i++)cube(0,1.1+i*.16,0,.14,.1,.14,
      i<lv?(on?[.25,.75,1]:[.1,.3,.4]):[.2,.2,.22]);return;}
  if(t==="drone_transporter"){cube(0,.1,0,CELL*.85,.2,CELL*.85,c);cyl(0,.55,0,.09,.9,[.3,.3,.34]);
    const p=A?(.6+.4*Math.abs(Math.sin(at*4))):.3;
    cube(0,1.05,0,.2,.2*p,.2,fcol||[.5,.5,.55]);return;}
  if(t==="drone_payload"){cube(0,.1,0,CELL*.95,.2,CELL*.95,c);
    cube(0,.22,0,CELL*.95,.05,.1,shade(c,.6));cube(0,.22,0,.1,.05,CELL*.95,shade(c,.6));
    cube(0,.3,0,.28,.1,.28,fcol||[.5,.5,.55]);return;}
  if(t==="air_separator"||t==="intake_pump_block"){cyl(0,0,0,CELL*.34,1.5,c);
    cyl(0,1.5,0,CELL*.38,.1,shade(c,.65));
    const sa=TA;TA=ang+(A?at*300:0);
    cube(0,1.68,0,.7,.05,.12,[.88,.9,.92]);cube(0,1.68,0,.12,.05,.7,[.88,.9,.92]);TA=sa;return;}
  if(t==="steam_cracker"){cube(0,.2,0,CELL*.9,.4,CELL*.9,c);
    cyl(-.35,.4,0,.22,1.5,shade(c,.7));cyl(.35,.4,0,.22,1.2,shade(c,.7));
    if(A){const p=.6+.4*Math.abs(Math.sin(at*3));cube(-.35,2,0,.2,.2,.2,[.9*p,.9*p,.95*p]);}return;}
  if(t==="electrolyzer"){cube(0,.35,0,CELL*.85,.7,CELL*.85,c);
    const b=A?(.5+.5*Math.abs(Math.sin(at*6))):.15;
    cyl(-.35,.7,0,.1,.6,[.8*b,.9*b,b]);cyl(.35,.7,0,.1,.6,[.35*b,.65*b,b]);
    cube(0,1.35,0,CELL*.6,.08,CELL*.3,[.3,.3,.34]);return;}
  if(t==="gas_cylinder_block"){cyl(0,0,0,.32,1.5,c);cyl(0,1.5,0,.36,.1,shade(c,.7));return;}
  if(t==="exhaust_pump_block"){cube(0,.2,0,CELL*.6,.4,CELL*.6,[.25,.24,.22]);
    cyl(0,.4,0,.2,1,c);cyl(0,1.4,0,.26,.12,[.1,.09,.08]);return;}
  if(t==="turbine_generator_block"){cube(0,.5,0,CELL*.8,1,CELL*.8,c);
    const p=A?(.5+.5*Math.abs(Math.sin(at*5))):.2;
    cyl(0,1,0,.22,.3,[.9*p,.75*p,.15*p],10);return;}
  if(t==="lathe"){cube(0,.35,0,CELL*.85,.7,CELL*.55,c);
    const sa=TA;TA=ang+(A?at*400:0);cyl(0,.55,0,.1,.35,[.75,.75,.78],6);TA=sa;return;}

  if(TANKS.has(t)){cyl(0,0,0,CELL*.4,1.1,c);cyl(0,1.1,0,CELL*.44,.1,shade(c,.65));
    if(A){const p=.5+.5*Math.abs(Math.sin(at*3.5));
      cyl(0,1.22,0,.18,.16,shade(lite,.6+p*.6),10);}return;}
  if(BOXES.has(t)){cube(0,.5,0,CELL*.8,1,CELL*.8,c);
    cube(0,1.03,0,CELL*.6,.07,CELL*.6,shade(c,.6));
    if(gauge!==null&&gauge!==undefined&&(t==="battery_cell"||t==="hv_battery")){
      const f=Math.max(0,Math.min(1,gauge));
      cube(0,1.15,0,CELL*.5*f+.05,.1,.18,[.25,.9,.45]);}
    if(A){const p=.5+.5*Math.abs(Math.sin(at*4));cube(0,1.12,CELL*.3,.16,.1,.06,[p,p*.9,.2]);}
    return;}
  /* fallback */
  cube(0,.5,0,CELL*.8,1,CELL*.8,c);
}

/* ===================== helpers ported from Python ===================== */
function familyCluster(W,pos,fam,core){
  const b=W.b.get(pos); if(!b||!fam.has(b.type))return [[],{}];
  const seen=new Set([pos]), cores=[], parts={};
  (b.type===core?cores:0)===cores?cores.push(pos):0;
  if(b.type!==core)(parts[b.type]=parts[b.type]||[]).push(pos);
  const st=[pos];
  while(st.length){const[cx,cz]=st.pop().split(",").map(Number);
    for(const[dx,dz]of DIRLIST){const np=key(cx+dx,cz+dz);
      if(seen.has(np))continue; const nb=W.b.get(np);
      if(nb&&fam.has(nb.type)){seen.add(np);
        if(nb.type===core)cores.push(np); else (parts[nb.type]=parts[nb.type]||[]).push(np);
        st.push(np);}}}
  return [cores,parts];
}
function burnerStats(W,pos){
  const b=W.b.get(pos); if(!b)return null;
  const base=D.FUEL_BURNERS[b.type]; if(!base)return null;
  const fi=FAMILY[b.type]; if(!fi)return base;
  const [fam,tbl]=fi;
  let p=base.power, po=base.pollution, fp=base.fuel_per_item;
  const [,parts]=familyCluster(W,pos,fam,b.type);
  for(const k in parts){const bo=tbl[k]||{};
    p+=bo.power||0; po+=bo.pollution||0; fp+=bo.fuel_per_item||0;}
  if(b.type==="coal_power_plant"&&parts.data_power_node){
    const lv=W.b.get(parts.data_power_node[0]).node_level||2;
    const m=D.COAL_PLANT_NODE_LEVEL_MULT[lv]||D.COAL_PLANT_NODE_LEVEL_MULT[2];
    p*=m.power; po*=m.pollution; fp*=m.fuel_per_item;}
  return {fuel_item:base.fuel_item,power:p,pollution:Math.max(0,po),fuel_per_item:Math.max(1,fp)};
}
function fmtAmt(t,n){n=n===undefined?1:n;
  return LIQUID.has(t)?`${lab(t)} ${(n*C.LITERS_PER_UNIT).toFixed(0)}L`:`${lab(t)} ${n}U`;}
const outList = o => Array.isArray(o)?o:[o];
const outLabels = o => outList(o).map(lab).join(", ");

/* ===================== World ===================== */
class World{
  constructor(){
    this.b=new Map(); this.items=[]; this.drones=[];
    this.money=30000; this.pol=0; this.sup=0; this.dem=0; this.eff=1;
    this.beff=new Map(); this.bflow=new Map(); this.rp=0; this.t=0;
  }
  add(gx,gz,type,dir){
    const cost=D.BUILD_COST[type], k=key(gx,gz);
    if(this.money<cost||this.b.has(k))return false;
    this.b.set(k,{type,gx,gz,dir:DIRS[dir]||dir,timer:0,processing_item:null,process_timer:0,
      fuel:0,buffer:{},charge:0,filter_item:null,drone_item:null,payload_count:0,
      node_level:2,drill_depth:1,drill_head:null,drill_head_durability:0,oil_boost:0,dynamite_boost:0});
    this.money-=cost; return true;
  }
  remove(gx,gz){this.b.delete(key(gx,gz));}

  computeEff(dt){
    const pos=[]; for(const[k,b]of this.b)if(POWER_NODES.has(b.type))pos.push(k);
    const set=new Set(pos), par=new Map(); pos.forEach(p=>par.set(p,p));
    const find=x=>{let r=x;while(par.get(r)!==r)r=par.get(r);
      while(par.get(x)!==r){const n=par.get(x);par.set(x,r);x=n;}return r;};
    for(const p of pos){const[gx,gz]=p.split(",").map(Number);
      for(const[dx,dz]of DIRLIST){const nb=key(gx+dx,gz+dz);
        if(set.has(nb)){const a=find(p),c=find(nb);if(a!==c)par.set(a,c);}}}
    const tr=pos.filter(p=>this.b.get(p).type==="transformer");
    for(let i=0;i<tr.length;i++){const[ax,az]=tr[i].split(",").map(Number);
      for(let j=i+1;j<tr.length;j++){const[bx,bz]=tr[j].split(",").map(Number);
        if(Math.max(Math.abs(ax-bx),Math.abs(az-bz))<=C.TRANSFORMER_RANGE){
          const a=find(tr[i]),c=find(tr[j]);if(a!==c)par.set(a,c);}}}
    const sup={},dem={},bat={};
    for(const p of pos){const b=this.b.get(p),t=b.type,r=find(p);
      let s=D.POWER_SUPPLY[t]||0;
      if(D.FUEL_BURNERS[t]&&b.fuel>0)s=burnerStats(this,p).power;
      sup[r]=(sup[r]||0)+s; dem[r]=(dem[r]||0)+(D.POWER_DRAW[t]||0);
      if(D.POWER_STORAGE[t])(bat[r]=bat[r]||[]).push(p);}
    const eff={},flow={};
    for(const r of new Set([...Object.keys(sup),...Object.keys(dem),...Object.keys(bat)])){
      const s=sup[r]||0,d=dem[r]||0,bp=bat[r]||[],net=s-d; flow[r]=net;
      if(net>=0){const room={};let tot=0;
        for(const p of bp){const b=this.b.get(p);const rm=D.POWER_STORAGE[b.type]-b.charge;room[p]=rm;tot+=rm;}
        if(tot>0){const add=Math.min(net*dt,tot);
          for(const p in room)if(room[p]>0)this.b.get(p).charge+=add*(room[p]/tot);}
        eff[r]=1;
      }else{const need=-net;const ch={};let tot=0;
        for(const p of bp){ch[p]=this.b.get(p).charge;tot+=ch[p];}
        let used=0;
        if(tot>0){used=Math.min(need*dt,tot);
          for(const p in ch)if(ch[p]>0)this.b.get(p).charge-=used*(ch[p]/tot);}
        const sat=s+(dt>0?used/dt:0);
        eff[r]=d<=0?1:Math.max(0,Math.min(1,sat/d));}}
    this.bflow=new Map(pos.map(p=>[p,flow[find(p)]]));
    return new Map(pos.map(p=>[p,eff[find(p)]]));
  }
  updatePower(dt){
    let sup=0,dem=0,coal=0,oil=0,ext=0,scrub=0,res=0,bp=0,fire=0;
    for(const[k,b]of this.b){const t=b.type;
      if(D.POWER_SUPPLY[t]){sup+=D.POWER_SUPPLY[t];
        if(t==="coal_gen")coal++; else if(t==="oil_gen")oil++;}
      if(D.POWER_DRAW[t]){dem+=D.POWER_DRAW[t];
        if(D.DEPOSIT_OUTPUT[t])ext++; else if(t==="scrubber")scrub++; else if(t==="research")res++;}
      if(D.FUEL_BURNERS[t]&&b.fuel>0){const s=burnerStats(this,k);sup+=s.power;bp+=s.pollution;}
      if(t==="firebox"&&b.processing_item!==null)fire++;}
    this.sup=sup; this.dem=dem; this.eff=dem<=0?1:Math.max(0,Math.min(1,sup/dem));
    this.beff=this.computeEff(dt);
    for(const[,b]of this.b)if(D.FUEL_BURNERS[b.type]&&b.fuel>0)b.fuel=Math.max(0,b.fuel-dt);
    this.pol+=(coal*C.COAL_POLLUTION_RATE+oil*C.OIL_GEN_POLLUTION_RATE+ext*C.MINER_POLLUTION_RATE
               +bp+fire*C.FIREBOX_POLLUTION_RATE)*dt;
    let red=0; for(const[k,b]of this.b)if(b.type==="scrubber")
      red+=C.SCRUBBER_POLLUTION_REDUCTION*(this.beff.get(k)||0);
    this.pol=Math.max(0,Math.min(100,this.pol-(C.POLLUTION_DECAY+red)*dt));
    for(const[k,b]of this.b)if(b.type==="research")this.rp+=C.RESEARCH_RP_RATE*dt*(this.beff.get(k)||0);
  }
  spawn(gx,gz,type,dir,off){this.items.push({x:gx*CELL,z:gz*CELL+(off||0),gx,gz,type,dir,src:key(gx,gz)});}
  updateExtractors(dt){
    for(const[k,b]of this.b){const t=b.type; if(!D.DEPOSIT_OUTPUT[t])continue;
      b.timer+=dt*(this.beff.get(k)||0);
      if(b.timer>=D.EXTRACT_INTERVAL[t]){b.timer=0;
        this.spawn(b.gx,b.gz,Object.values(D.DEPOSIT_OUTPUT[t])[0],b.dir,0);}}
  }
  updateProcessors(dt){
    for(const[k,b]of this.b){ if(!D.PROCESS_TIME[b.type])continue;
      if(b.processing_item!==null){
        b.process_timer+=dt*(this.beff.get(k)||0);
        if(b.process_timer>=D.PROCESS_TIME[b.type]){
          const outs=outList(b.processing_item); b.processing_item=null; b.process_timer=0;
          outs.forEach((o,i)=>this.spawn(b.gx,b.gz,o,b.dir,(i-(outs.length-1)/2)*.35));}}}
  }
  updateDrills(dt){
    for(const[k,b]of this.b){ if(b.type!=="mineshaft_drill")continue;
      if(!b.drill_head)continue;
      const e=this.beff.get(k)||0; if(e<=0)continue;
      const oiled=b.oil_boost>0, dyn=b.dynamite_boost>0;
      let iv=C.MINESHAFT_BASE_INTERVAL; if(oiled)iv*=.5; if(dyn)iv*=.5;
      b.timer+=dt*e; if(b.timer<iv)continue; b.timer=0;
      const dep=b.drill_depth;
      if(D.DRILL_HEAD_MIN_DEPTH[b.drill_head]<dep)continue;
      b.drill_head_durability-=1+(oiled?C.OIL_WEAR_BONUS:0);
      if(oiled)b.oil_boost--; if(dyn)b.dynamite_boost--;
      const pool=D.DRILL_DEPTH_OUTPUTS[dep];
      let tot=0;for(const p of pool)tot+=p[1];
      let r=Math.random()*tot, out=pool[0][0];
      for(const p of pool){r-=p[1]; if(r<=0){out=p[0];break;}}
      this.spawn(b.gx,b.gz,out,b.dir,0);
      if(oiled&&Math.random()<C.OIL_YIELD_BONUS)this.spawn(b.gx,b.gz,out,b.dir,.3);
      if(b.drill_head_durability<=0){b.drill_head=null;b.drill_head_durability=0;}}
  }
  updateDroneTx(dt){
    for(const[k,b]of this.b){ if(b.type!=="drone_transporter")continue;
      b.timer+=dt; if(b.timer<C.DRONE_SCAN_INTERVAL||!b.drone_item)continue; b.timer=0;
      const want=b.drone_item; let dest=null,dd=null;
      for(const[k2,b2]of this.b)if(b2.type==="drone_payload"&&b2.drone_item===want){
        const d=Math.max(Math.abs(b2.gx-b.gx),Math.abs(b2.gz-b.gz));
        if(d<=C.DRONE_RANGE&&(dd===null||d<dd)){dd=d;dest=b2;}}
      if(!dest)continue;
      let bi=null,bd=null;
      for(let i=0;i<this.items.length;i++){const it=this.items[i];
        if(it.type!==want)continue;
        const d=Math.max(Math.abs(it.gx-b.gx),Math.abs(it.gz-b.gz));
        if(d<=C.DRONE_RANGE&&(bd===null||d<bd)){bd=d;bi=i;}}
      if(bi===null)continue;
      const p=this.items.splice(bi,1)[0];
      this.drones.push({sx:b.gx*CELL,sz:b.gz*CELL,tx:dest.gx*CELL,tz:dest.gz*CELL,
        to:key(dest.gx,dest.gz),item:p.type,prog:0});}
  }
  updateDrones(dt){
    this.drones=this.drones.filter(d=>{
      const dist=Math.max(1e-6,Math.hypot(d.tx-d.sx,d.tz-d.sz));
      d.prog+=C.DRONE_FLIGHT_SPEED*dt/dist;
      if(d.prog>=1){const b=this.b.get(d.to);
        if(b&&b.type==="drone_payload")b.payload_count++; return false;}
      return true;});
  }
  updatePayloads(dt){
    for(const[k,b]of this.b){ if(b.type!=="drone_payload")continue;
      if(b.payload_count<=0||!b.drone_item)continue;
      b.timer+=dt;
      if(b.timer>=C.DRONE_EMIT_INTERVAL){b.timer=0;b.payload_count--;
        this.spawn(b.gx,b.gz,b.drone_item,b.dir,0);}}
  }
  moveItems(dt){
    const mult=Math.max(.2,1-this.pol/100), alive=[];
    for(const it of this.items){
      const b=this.b.get(key(it.gx,it.gz)); if(!b)continue;
      const t=b.type;
      if(t==="depot"){this.money+=(D.SELL_PRICE[it.type]||2)*mult;continue;}
      const own=it.src===key(it.gx,it.gz);
      const flow=()=>{const[dx,dz]=b.dir;it.dir=[dx,dz];
        it.x+=dx*C.ITEM_SPEED*dt;it.z+=dz*C.ITEM_SPEED*dt;
        it.gx=Math.round(it.x/CELL);it.gz=Math.round(it.z/CELL);alive.push(it);};
      if(CONVEYOR_LIKE.has(t)||D.DEPOSIT_OUTPUT[t]){flow();continue;}
      if(PIPE_LIKE.has(t)){if(!LIQUID.has(it.type))continue;flow();continue;}
      if(t==="gas_input_block"){
        if(it.type===D.FUEL_BURNERS.gas_turbine.fuel_item){alive.push(it);continue;}flow();continue;}
      if(t==="turbine_hp_stage"){
        if(it.type===D.FUEL_BURNERS.modular_turbine.fuel_item){alive.push(it);continue;}flow();continue;}
      if(t==="mineshaft_drill"){
        const w=has(D.DRILL_HEAD_DURABILITY,it.type)||["acid","machine_oil","dynamite"].includes(it.type);
        if(!own&&w)alive.push(it); else flow(); continue;}
      if(t==="item_filter"){
        if(b.filter_item&&it.type!==b.filter_item)continue; flow(); continue;}
      if(CROSSROAD.has(t)){
        if(t==="pipe_crossroad"&&!LIQUID.has(it.type))continue;
        const[dx,dz]=it.dir||b.dir;it.x+=dx*C.ITEM_SPEED*dt;it.z+=dz*C.ITEM_SPEED*dt;
        it.gx=Math.round(it.x/CELL);it.gz=Math.round(it.z/CELL);alive.push(it);continue;}
      if(has(D.DYNAMIC_RECIPES,t)){
        if(!own&&has(D.DYNAMIC_INPUT_MAX[t],it.type))alive.push(it); else flow(); continue;}
      if(t==="blast_furnace"){
        if(!own&&(has(D.BLAST_FURNACE_PRIMARY,it.type)||FUEL_LIKE.has(it.type)))alive.push(it);
        else flow(); continue;}
      if(has(D.RECIPES,t)){
        if(has(D.RECIPES[t],it.type))alive.push(it); else flow(); continue;}
      if(has(D.MULTI_RECIPES,t)){
        if(has(D.MULTI_RECIPES[t].inputs,it.type))alive.push(it); else flow(); continue;}
      if(D.FUEL_BURNERS[t]){
        if(it.type===D.FUEL_BURNERS[t].fuel_item)alive.push(it); else flow(); continue;}
      /* solar / research / scrubber etc -> lost */
    }
    this.items=alive;
  }
  capture(){
    const rest=[];
    for(const it of this.items){
      const k=key(it.gx,it.gz), b=this.b.get(k); let got=false;
      if(b){
        const dx=it.x-it.gx*CELL, dz=it.z-it.gz*CELL;
        const near=Math.hypot(dx,dz)<=C.CAPTURE_RADIUS, t=b.type;
        const own=it.src===k;
        if(has(D.RECIPES,t)&&b.processing_item===null){
          const r=D.RECIPES[t];
          if(has(r,it.type)&&near){b.processing_item=r[it.type];b.process_timer=0;got=true;}
        }else if(has(D.MULTI_RECIPES,t)&&b.processing_item===null){
          const r=D.MULTI_RECIPES[t], need=r.inputs;
          if(has(need,it.type)&&near){
            const have=b.buffer[it.type]||0;
            if(have<need[it.type]){b.buffer[it.type]=have+1;got=true;
              if(Object.keys(need).every(x=>(b.buffer[x]||0)>=need[x])){
                for(const x in need)b.buffer[x]-=need[x];
                b.processing_item=r.output;b.process_timer=0;}}}
        }else if(t==="blast_furnace"&&b.processing_item===null){
          if(!own&&near){
            if(has(D.BLAST_FURNACE_PRIMARY,it.type)){
              const cur=b.buffer.primary_item;
              if((cur===undefined||cur===it.type)&&(b.buffer.primary||0)<1){
                b.buffer.primary_item=it.type;b.buffer.primary=1;got=true;}
            }else if(FUEL_LIKE.has(it.type)){
              if((b.buffer.fuel||0)<1){b.buffer.fuel=1;got=true;}}
            if((b.buffer.primary||0)>=1&&(b.buffer.fuel||0)>=1){
              b.processing_item=D.BLAST_FURNACE_PRIMARY[b.buffer.primary_item];
              b.process_timer=0;b.buffer={};}}
        }else if(has(D.DYNAMIC_RECIPES,t)&&b.processing_item===null){
          const lim=D.DYNAMIC_INPUT_MAX[t];
          if(!own&&has(lim,it.type)&&near){
            const have=b.buffer[it.type]||0;
            if(have<lim[it.type]){b.buffer[it.type]=have+1;got=true;
              for(const r of D.DYNAMIC_RECIPES[t]){const need=r.inputs;
                if(Object.keys(need).every(x=>(b.buffer[x]||0)>=need[x])){
                  for(const x in need)b.buffer[x]-=need[x];
                  b.processing_item=r.output;b.process_timer=0;break;}}}}
        }else if(D.FUEL_BURNERS[t]&&it.type===D.FUEL_BURNERS[t].fuel_item&&near){
          b.fuel+=burnerStats(this,k).fuel_per_item; got=true;
        }else if(t==="gas_input_block"&&it.type===D.FUEL_BURNERS.gas_turbine.fuel_item&&near){
          const[cores]=familyCluster(this,k,FAMILY.gas_turbine[0],"gas_turbine");
          if(cores.length){const sh=burnerStats(this,cores[0]).fuel_per_item/cores.length;
            cores.forEach(p=>this.b.get(p).fuel+=sh); got=true;}
        }else if(t==="turbine_hp_stage"&&it.type===D.FUEL_BURNERS.modular_turbine.fuel_item&&near){
          const[cores]=familyCluster(this,k,FAMILY.modular_turbine[0],"modular_turbine");
          if(cores.length){const sh=burnerStats(this,cores[0]).fuel_per_item/cores.length;
            cores.forEach(p=>this.b.get(p).fuel+=sh); got=true;}
        }else if(t==="mineshaft_drill"&&near){
          if(has(D.DRILL_HEAD_DURABILITY,it.type)){
            if(!b.drill_head){b.drill_head=it.type;
              b.drill_head_durability=D.DRILL_HEAD_DURABILITY[it.type];got=true;}
          }else if(it.type==="acid"){
            if(b.drill_head){b.drill_head_durability+=C.ACID_DURABILITY_BONUS;got=true;}
          }else if(it.type==="machine_oil"){b.oil_boost=C.OIL_BOOST_CYCLES;got=true;}
          else if(it.type==="dynamite"){b.dynamite_boost=C.DYNAMITE_BOOST_CYCLES;got=true;}}
      }
      if(!got)rest.push(it);
    }
    this.items=rest;
  }
  update(dt){
    this.t+=dt; this.updatePower(dt); this.updateExtractors(dt); this.updateProcessors(dt);
    this.updateDrills(dt); this.updateDroneTx(dt); this.updateDrones(dt); this.updatePayloads(dt);
    this.moveItems(dt); this.capture();
  }
}

/* ===================== info panels ===================== */
function menuInfo(t){
  const L=[`<div class="t">${D.BUILD_LABEL[t]}</div>`,
           `<div>가격: <b>$${D.BUILD_COST[t]}</b></div>`];
  if(D.BUILD_DESC[t])L.push(`<div class="d">${D.BUILD_DESC[t]}</div>`);
  const P=[];
  if(D.POWER_DRAW[t])P.push(`소모 <span class="k">${D.POWER_DRAW[t].toFixed(1)}</span> MF/s`);
  if(D.POWER_SUPPLY[t])P.push(`공급 <span class="k">${D.POWER_SUPPLY[t].toFixed(1)}</span> MF/s`);
  if(D.POWER_STORAGE[t])P.push(`저장 <span class="k">${D.POWER_STORAGE[t]}</span> MF`);
  if(P.length)L.push("<div>전력: "+P.join(" · ")+"</div>");
  if(D.DEPOSIT_OUTPUT[t])L.push(`<div>채굴: <b>${[...new Set(Object.values(D.DEPOSIT_OUTPUT[t]).map(lab))].join(", ")}</b> (어디든 설치 가능)</div>`);
  if(has(D.RECIPES,t))for(const i in D.RECIPES[t])
    L.push(`<div>${lab(i)} → <b>${outLabels(D.RECIPES[t][i])}</b></div>`);
  if(has(D.MULTI_RECIPES,t)){const r=D.MULTI_RECIPES[t];
    L.push(`<div>${Object.entries(r.inputs).map(([k,v])=>lab(k)+(v>1?` ${v}개`:"")).join(" + ")} → <b>${outLabels(r.output)}</b></div>`);}
  if(has(D.DYNAMIC_RECIPES,t))for(const r of D.DYNAMIC_RECIPES[t])
    L.push(`<div>${Object.entries(r.inputs).map(([k,v])=>lab(k)+(v>1?` ${v}개`:"")).join(" + ")} → <b>${outLabels(r.output)}</b></div>`);
  if(t==="blast_furnace"){const f=[...FUEL_LIKE].map(lab).join(" 또는 ");
    for(const p in D.BLAST_FURNACE_PRIMARY)
      L.push(`<div>${lab(p)} + ${f} → <b>${lab(D.BLAST_FURNACE_PRIMARY[p])}</b></div>`);}
  if(D.FUEL_BURNERS[t]){const i=D.FUEL_BURNERS[t];
    L.push(`<div>연료: <b>${lab(i.fuel_item)}</b> (1개당 ${i.fuel_per_item.toFixed(1)}초)</div>`);
    L.push(`<div>발전 <span class="k">${i.power}</span> MF/s · 오염 ${i.pollution.toFixed(2)}/s</div>`);}
  for(const core in FAMILY){const tbl=FAMILY[core][1];
    if(has(tbl,t)){const b=tbl[t],p=[];
      if(b.power)p.push(`발전량 +${b.power}`);
      if(b.pollution)p.push(`오염 ${b.pollution>0?"+":""}${b.pollution.toFixed(2)}/s`);
      if(b.fuel_per_item)p.push(`연료효율 +${b.fuel_per_item}초`);
      L.push(`<div><b>${D.BUILD_LABEL[core]}</b>에 인접 시: ${p.join(", ")}</div>`);break;}}
  if(t==="mineshaft_drill"){
    L.push(`<div class="d" style="margin-top:6px">드릴 헤드 필요 · <span class="k">T</span>로 깊이 변경</div>`);
    for(const h in D.DRILL_HEAD_MIN_DEPTH)
      L.push(`<div>· ${lab(h)}: 내구 ${D.DRILL_HEAD_DURABILITY[h]}, ${D.DRILL_DEPTH_LABEL[D.DRILL_HEAD_MIN_DEPTH[h]]}까지</div>`);
    for(const d in D.DRILL_DEPTH_OUTPUTS)
      L.push(`<div>${D.DRILL_DEPTH_LABEL[d]}: ${D.DRILL_DEPTH_OUTPUTS[d].map(p=>lab(p[0])).join(", ")}</div>`);
    L.push(`<div class="d">산 +${C.ACID_DURABILITY_BONUS} 내구 · 머신오일 ${C.OIL_BOOST_CYCLES}사이클 2배속+증산 · 다이너마이트 ${C.DYNAMITE_BOOST_CYCLES}사이클 2배속</div>`);}
  if(t==="scrubber")L.push(`<div>오염 감소 <span class="k">${C.SCRUBBER_POLLUTION_REDUCTION}</span>/s</div>`);
  if(t==="research")L.push(`<div>RP 생산 <span class="k">${C.RESEARCH_RP_RATE}</span>/s</div>`);
  if(t==="item_filter")L.push(`<div class="d">조준 후 <span class="k">F</span>로 통과시킬 아이템 지정</div>`);
  if(DRONE_UI.has(t))L.push(`<div class="d">조준 후 <span class="k">G</span>로 아이템 지정</div>`);
  if(t==="data_power_node")L.push(`<div class="d">조준 후 <span class="k">T</span>로 출력 단계 변경</div>`);
  return L.join("");
}
function aimInfo(W,gx,gz){
  const k=key(gx,gz), b=W.b.get(k); if(!b)return null;
  const t=b.type, L=[`<div class="t">${D.BUILD_LABEL[t]}</div>`];
  if(POWER_NODES.has(t)){const e=W.beff.get(k);
    if(e!==undefined)L.push(`가동률: ${(e*100).toFixed(0)}%`);}
  if(D.FUEL_BURNERS[t]){const i=burnerStats(W,k);
    L.push(`연료: ${b.fuel.toFixed(1)}s / ${i.fuel_per_item.toFixed(1)}s`);
    if(FAMILY[t]){const[,parts]=familyCluster(W,k,FAMILY[t][0],t);
      const ns=Object.keys(parts).map(p=>D.BUILD_LABEL[p]||p).sort();
      L.push(`발전량: ${i.power.toFixed(0)} MF ${ns.length?`(부품: ${ns.join(", ")})`:"(부품 없음)"}`);}}
  if(t==="gas_input_block"){const[c]=familyCluster(W,k,FAMILY.gas_turbine[0],"gas_turbine");
    L.push(c.length?`연결된 가스터빈: ${c.length}개`:"연결된 가스터빈 없음");}
  if(S(D.COAL_PLANT_FAMILY).has(t)&&t!=="coal_power_plant"){
    const[c]=familyCluster(W,k,FAMILY.coal_power_plant[0],"coal_power_plant");
    if(t!=="heat_exchanger")L.push(c.length?`연결된 발전소: ${c.length}개`:"연결된 발전소 없음");
    if(t==="heat_exchanger")L.push("물이 들어오면 고압 증기로 바꿈 (전력 필요)");
    if(t==="data_power_node"){const m={1:"저출력 (절약)",2:"표준",3:"고출력 (오염↑)"};
      L.push(`출력 단계: <b>${m[b.node_level]}</b> (T로 변경)`);}}
  if(S(D.MODULAR_TURBINE_FAMILY).has(t)&&t!=="modular_turbine"){
    const[c]=familyCluster(W,k,FAMILY.modular_turbine[0],"modular_turbine");
    L.push(c.length?`연결된 모듈러 터빈: ${c.length}개`:"연결된 터빈 없음");
    if(t==="turbine_hp_stage")L.push("터빈 인풋: 고압 증기를 파이프로 연결");}
  if(t==="mineshaft_drill"){
    L.push(`채굴 깊이: <b>${D.DRILL_DEPTH_LABEL[b.drill_depth]}</b> (T로 변경)`);
    if(!b.drill_head)L.push("<span style='color:#ff9a8a'>드릴 헤드 없음</span>");
    else{L.push(`드릴 헤드: ${lab(b.drill_head)} (${b.drill_head_durability.toFixed(0)}/${D.DRILL_HEAD_DURABILITY[b.drill_head]})`);
      if(D.DRILL_HEAD_MIN_DEPTH[b.drill_head]<b.drill_depth)
        L.push("<span style='color:#ff9a8a'>이 헤드로는 이 깊이 불가 - 대기 중</span>");}
    const bo=[]; if(b.oil_boost>0)bo.push(`머신오일 ${b.oil_boost}`);
    if(b.dynamite_boost>0)bo.push(`다이너마이트 ${b.dynamite_boost}`);
    if(bo.length)L.push("효과: "+bo.join(", "));}
  if(D.POWER_STORAGE[t])L.push(`충전량: ${b.charge.toFixed(0)} / ${D.POWER_STORAGE[t]} MF`);
  if(t==="power_meter"){const f=W.bflow.get(k)||0;
    L.push(`순 발전량: ${f>=0?"+":""}${f.toFixed(1)} MF/s`);}
  if(t==="item_filter")L.push(`필터: <b>${b.filter_item?lab(b.filter_item):"없음 (전부 통과)"}</b> (F로 변경)`);
  if(t==="drone_transporter")L.push(`운반 대상: <b>${b.drone_item?lab(b.drone_item):"없음"}</b> (G로 변경)`);
  if(t==="drone_payload"){L.push(`수신 대상: <b>${b.drone_item?lab(b.drone_item):"없음"}</b> (G로 변경)`);
    L.push(`대기중: ${b.payload_count}개`);}
  if((has(D.MULTI_RECIPES,t)||has(D.DYNAMIC_RECIPES,t))&&b.buffer){
    const p=Object.entries(b.buffer).filter(([,v])=>v>0).map(([k2,v])=>fmtAmt(k2,v));
    if(p.length)L.push("모인 재료: "+p.join(", "));}
  if(t==="blast_furnace"&&b.buffer){const p=[];
    if(b.buffer.primary>0)p.push(fmtAmt(b.buffer.primary_item));
    if(b.buffer.fuel>0)p.push("연료 1개");
    if(p.length)L.push("모인 재료: "+p.join(", "));}
  if(b.processing_item!==null)L.push("가공중: "+outList(b.processing_item).map(x=>fmtAmt(x)).join(", "));
  if(D.DEPOSIT_OUTPUT[t])L.push("채굴 중: "+lab(Object.values(D.DEPOSIT_OUTPUT[t])[0]));
  for(const it of W.items)if(it.gx===gx&&it.gz===gz){L.push("지나가는 중: "+fmtAmt(it.type));break;}
  return L.join("<br>");
}

/* ===================== game state / input ===================== */
const W = new World();
let px=0, py=1.6, pz=8, yaw=-90, pitch=0;
let sel="coal_miner", faceOff=0, locked=false;
let bmenuOn=false, imenuOn=false, imenuMode=null, imenuTarget=null, detailType=null;
const keys={};
const $=id=>document.getElementById(id);

function toast(m){const e=$("toast");e.textContent=m;e.classList.add("on");
  clearTimeout(toast._t);toast._t=setTimeout(()=>e.classList.remove("on"),1400);}
function snapDir(y){y=((y%360)+360)%360;
  if(y>=45&&y<135)return"S"; if(y>=135&&y<225)return"W"; if(y>=225&&y<315)return"N"; return"E";}
function rotDir(d,n){const o=["E","S","W","N"];return o[(o.indexOf(d)+n)%4];}
function targetCell(){
  const fx=Math.cos(yaw*Math.PI/180), fz=Math.sin(yaw*Math.PI/180);
  return [Math.round((px+fx*C.PLACE_DISTANCE)/CELL), Math.round((pz+fz*C.PLACE_DISTANCE)/CELL)];
}
function anyMenu(){return bmenuOn||imenuOn;}

/* ---- build menu ---- */
function buildMenu(){
  const wrap=$("bbody"); wrap.innerHTML="";
  for(const[gname,items]of D.BUILD_GROUPS){
    const g=document.createElement("div");g.className="grp";g.textContent=gname;wrap.appendChild(g);
    const row=document.createElement("div");row.className="btns";
    for(const t of items){
      const c=D.BUILD_COLOR[t], cost=D.BUILD_COST[t];
      const b=document.createElement("div");
      b.className="bbtn"+(t===sel?" sel":"")+(W.money<cost?" poor":"");
      b.style.background=`linear-gradient(160deg,rgba(${c.map(v=>(v*255)|0).join(",")},.95),rgba(${c.map(v=>(v*150)|0).join(",")},.95))`;
      b.innerHTML=`<div class="n">${D.BUILD_LABEL[t]}</div><div class="c">$${cost}</div>`;
      b.onclick=()=>{sel=t;closeMenus();updateSel();};
      b.oncontextmenu=e=>{e.preventDefault();
        detailType=detailType===t?null:t;renderDetail();
        wrap.querySelectorAll(".bbtn").forEach(x=>x.classList.remove("det"));
        if(detailType===t)b.classList.add("det");};
      row.appendChild(b);}
    wrap.appendChild(row);}
}
function renderDetail(){const d=$("detail");
  if(!detailType||!bmenuOn){d.style.display="none";return;}
  d.innerHTML=menuInfo(detailType); d.style.display="block";}
function updateSel(){$("s-name").textContent=D.BUILD_LABEL[sel];
  $("s-cost").textContent=`($${D.BUILD_COST[sel]})`;}

/* ---- item picker (filter / drone) ---- */
function openItemMenu(mode,target){
  imenuMode=mode; imenuTarget=target; imenuOn=true;
  const b=W.b.get(target);
  $("ihead").textContent = mode==="filter" ? "필터로 통과시킬 아이템 선택"
    : (b.type==="drone_transporter" ? "드론이 가져올 아이템 선택" : "드론 페이로드가 받을 아이템 선택");
  const cur = mode==="filter" ? b.filter_item : b.drone_item;
  const body=$("ibody"); body.innerHTML="";
  const clr=document.createElement("div");clr.className="ibtn clr";
  clr.textContent="— 지정 해제 —";
  clr.onclick=()=>{pick(null);};
  body.appendChild(clr);
  const list=Object.keys(D.ITEM_LABEL).sort((a,c)=>lab(a).localeCompare(lab(c),"ko"));
  for(const t of list){
    const col=D.ITEM_COLOR[t]||[.5,.5,.5];
    const e=document.createElement("div");e.className="ibtn"+(t===cur?" sel":"");
    e.innerHTML=`<span class="sw" style="background:rgb(${col.map(v=>(v*255)|0).join(",")})"></span>${lab(t)}`;
    e.onclick=()=>pick(t); body.appendChild(e);}
  $("imenu").classList.add("on"); document.exitPointerLock();
}
function pick(t){const b=W.b.get(imenuTarget);
  if(b){if(imenuMode==="filter")b.filter_item=t; else b.drone_item=t;}
  closeMenus(); relock();}
function closeMenus(){bmenuOn=false;imenuOn=false;detailType=null;
  $("bmenu").classList.remove("on");$("imenu").classList.remove("on");$("detail").style.display="none";}
function relock(){if(!anyMenu())tryLock();}
/* clicking the dimmed backdrop closes a menu too (extra way out) */
for(const id of ["bmenu","imenu"])
  $(id).addEventListener("mousedown",e=>{if(e.target===$(id)){closeMenus();relock();}});

/* ---- input ----
   Pointer lock is preferred, but browsers refuse it on some file:// pages, so
   everything degrades gracefully: WASD always works, and looking around falls
   back to click-drag when the pointer isn't locked. */
let started=false, dragging=false, lastMX=0, lastMY=0, dragDist=0;
const tryLock=()=>{try{cv.requestPointerLock();}catch(_){}};
$("startb").onclick=()=>{$("start").style.display="none";started=true;tryLock();};
document.addEventListener("pointerlockchange",()=>{locked=document.pointerLockElement===cv;});
document.addEventListener("mousemove",e=>{
  if(anyMenu()||!started)return;
  if(locked){
    yaw+=e.movementX*C.MOUSE_SENS; pitch-=e.movementY*C.MOUSE_SENS;
  }else if(dragging){
    const dx=e.clientX-lastMX, dy=e.clientY-lastMY;
    dragDist+=Math.abs(dx)+Math.abs(dy);
    yaw+=dx*C.MOUSE_SENS*1.6; pitch-=dy*C.MOUSE_SENS*1.6;
    lastMX=e.clientX; lastMY=e.clientY;
  }else return;
  pitch=Math.max(-89,Math.min(89,pitch));
});
cv.addEventListener("mousedown",e=>{
  if(anyMenu()||!started)return;
  if(!locked){                      // not locked: try to lock, and drag to look
    dragging=true; dragDist=0; lastMX=e.clientX; lastMY=e.clientY;
    if(e.button===0)tryLock();
  }
});
document.addEventListener("mouseup",()=>{dragging=false;});
/* place on click release, but not when the click was really a drag-to-look */
cv.addEventListener("click",e=>{
  if(anyMenu()||!started)return;
  if(!locked&&dragDist>6){dragDist=0;return;}
  dragDist=0;
  const[gx,gz]=targetCell();
  if(!W.add(gx,gz,sel,rotDir(snapDir(yaw),faceOff)))
    toast(W.money<D.BUILD_COST[sel]?"자금 부족":"이미 건물이 있음");
});
cv.addEventListener("auxclick",e=>{if(e.button===1&&!anyMenu())e.preventDefault();});
cv.addEventListener("contextmenu",e=>{
  e.preventDefault(); if(anyMenu()||!started)return;
  const[gx,gz]=targetCell(); W.remove(gx,gz);
});
document.addEventListener("keydown",e=>{
  const k=e.key.toLowerCase(); keys[k]=true;
  if(k==="escape"){if(anyMenu()){closeMenus();relock();}return;}
  /* B toggles the build menu BOTH ways. This is checked before the anyMenu()
     guard on purpose - otherwise the menu can only be closed with ESC, and a
     player who opens it with B and presses B again is stuck unable to move. */
  if(k==="b"&&!imenuOn){
    e.preventDefault();
    if(bmenuOn){closeMenus();relock();}
    else{bmenuOn=true;$("bmenu").classList.add("on");buildMenu();document.exitPointerLock();}
    return;}
  if(anyMenu())return;
  const[gx,gz]=targetCell(), b=W.b.get(key(gx,gz));
  if(k==="r"){faceOff=(faceOff+1)%4;}
  else if(k==="f"){if(b&&b.type==="item_filter")openItemMenu("filter",key(gx,gz));else toast("아이템 필터를 조준하세요");}
  else if(k==="g"){if(b&&DRONE_UI.has(b.type))openItemMenu("drone",key(gx,gz));else toast("드론 수송기/페이로드를 조준하세요");}
  else if(k==="t"){
    if(b&&b.type==="data_power_node"){b.node_level=b.node_level%3+1;toast("출력 단계: "+({1:"저출력",2:"표준",3:"고출력"})[b.node_level]);}
    else if(b&&b.type==="mineshaft_drill"){b.drill_depth=b.drill_depth%4+1;toast("채굴 깊이: "+D.DRILL_DEPTH_LABEL[b.drill_depth]);}
    else toast("데이터 파워 노드/마인샤프트 드릴을 조준하세요");}
  else if(k==="2"){sel="wire";updateSel();}
  else if(k==="3"){sel="pipe";updateSel();}
});
document.addEventListener("keyup",e=>{keys[e.key.toLowerCase()]=false;});
window.addEventListener("resize",resize);
function resize(){const d=Math.min(window.devicePixelRatio||1,2);
  cv.width=Math.floor(innerWidth*d);cv.height=Math.floor(innerHeight*d);
  gl.viewport(0,0,cv.width,cv.height);}
resize();

/* ===================== ground (static) ===================== */
const EXT=GR*CELL;
let groundBuf=null, groundN=0, gridBuf=null, gridN=0;
function buildStatic(){
  reset(); const g=[.30,.62,.30];
  vtx(-EXT,0,-EXT,...g);vtx(EXT,0,-EXT,...g);vtx(EXT,0,EXT,...g);
  vtx(-EXT,0,-EXT,...g);vtx(EXT,0,EXT,...g);vtx(-EXT,0,EXT,...g);
  groundN=vn; groundBuf=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,groundBuf);
  gl.bufferData(gl.ARRAY_BUFFER,VB.subarray(0,vn*6),gl.STATIC_DRAW); vn=0;
  reset(); const c=[.92,.94,.90];
  for(let i=-GR;i<=GR;i++){const p=i*CELL;
    vtx(p,.01,-EXT,...c);vtx(p,.01,EXT,...c);
    vtx(-EXT,.01,p,...c);vtx(EXT,.01,p,...c);}
  gridN=vn; gridBuf=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,gridBuf);
  gl.bufferData(gl.ARRAY_BUFFER,VB.subarray(0,vn*6),gl.STATIC_DRAW); vn=0;
}
function drawStatic(b,n,mode,tint){
  if(!n)return; gl.bindBuffer(gl.ARRAY_BUFFER,b);
  gl.vertexAttribPointer(aP,3,gl.FLOAT,false,24,0);
  gl.vertexAttribPointer(aC,3,gl.FLOAT,false,24,12);
  gl.drawArrays(mode,0,n);
}
buildStatic();

/* ===================== main loop ===================== */
let last=performance.now(), fpsT=0, fpsN=0, fpsV=0;
function frame(now){
  let dt=(now-last)/1000; last=now; dt=Math.min(dt,.1);
  fpsT+=dt; fpsN++; if(fpsT>=.5){fpsV=fpsN/fpsT;fpsT=0;fpsN=0;$("fps").textContent="FPS "+fpsV.toFixed(0);}

  /* movement - works with or without pointer lock */
  if(started&&!anyMenu()){
    const sp=C.MOVE_SPEED*(keys["shift"]?C.SPRINT_MULT:1)*dt;
    const fx=Math.cos(yaw*Math.PI/180), fz=Math.sin(yaw*Math.PI/180);
    const rx=Math.cos((yaw-90)*Math.PI/180), rz=Math.sin((yaw-90)*Math.PI/180);
    if(keys["w"]){px+=fx*sp;pz+=fz*sp;} if(keys["s"]){px-=fx*sp;pz-=fz*sp;}
    if(keys["a"]){px-=rx*sp;pz-=rz*sp;} if(keys["d"]){px+=rx*sp;pz+=rz*sp;}
    const lim=EXT-.5; px=Math.max(-lim,Math.min(lim,px)); pz=Math.max(-lim,Math.min(lim,pz));
  }
  W.update(dt);

  /* camera + fog */
  const t=W.pol/100;
  const sky=[.53+.15*t, .80-.35*t, .92-.45*t];
  gl.clearColor(sky[0],sky[1],sky[2],1);
  gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
  gl.uniform3fv(uFog,sky); gl.uniform1f(uDen,.0065+t*.022); gl.uniform3f(uCam,px,py,pz);
  const cy=Math.cos(pitch*Math.PI/180);
  const P=m4persp(70,cv.width/cv.height,.1,340);
  const V=m4look(px,py,pz, px+Math.cos(yaw*Math.PI/180)*cy, py+Math.sin(pitch*Math.PI/180),
                 pz+Math.sin(yaw*Math.PI/180)*cy);
  gl.uniformMatrix4fv(uVP,false,m4mul(P,V));

  /* ground */
  const gc=[.30+(.42-.30)*t, .62+(.38-.62)*t, .30+(.32-.30)*t];
  reset();
  vtx(-EXT,0,-EXT,...gc);vtx(EXT,0,-EXT,...gc);vtx(EXT,0,EXT,...gc);
  vtx(-EXT,0,-EXT,...gc);vtx(EXT,0,EXT,...gc);vtx(-EXT,0,EXT,...gc);
  flush(gl.TRIANGLES);
  drawStatic(gridBuf,gridN,gl.LINES);

  /* buildings */
  reset();
  const [tgx,tgz]=targetCell();
  const R=52*CELL, R2=R*R;
  for(const[k,b]of W.b){
    const wx=b.gx*CELL, wz=b.gz*CELL;
    const ddx=wx-px, ddz=wz-pz; if(ddx*ddx+ddz*ddz>R2)continue;
    const ty=b.type;
    const active = D.POWER_DRAW[ty] ? (W.beff.get(k)||0)>.01 : true;
    let gauge=null;
    if(ty==="power_meter")gauge=W.bflow.get(k)||0;
    else if(D.POWER_STORAGE[ty])gauge=b.charge/D.POWER_STORAGE[ty];
    else if(ty==="data_power_node")gauge=b.node_level;
    else if(ty==="mineshaft_drill")gauge=b.drill_depth;
    let conn=null;
    if(ty==="pipe")conn=DIRLIST.filter(([dx,dz])=>{
      const n=W.b.get(key(b.gx+dx,b.gz+dz));return n&&PIPE_CONNECTABLE.has(n.type);});
    let fc=null;
    if(ty==="item_filter")fc=D.ITEM_COLOR[b.filter_item]||null;
    else if(DRONE_UI.has(ty))fc=D.ITEM_COLOR[b.drone_item]||null;
    else if(ty==="mineshaft_drill")fc=D.ITEM_COLOR[b.drill_head]||null;
    const ang={"1,0":0,"0,-1":90,"-1,0":180,"0,1":270}[b.dir.join(",")]||0;
    model(ty,wx,wz,ang,W.t,active,gauge,conn,fc);
    TX=wx;TY=0;TZ=wz;TA=0;
    if(b.processing_item!==null){
      const o=outList(b.processing_item)[0], pc=D.ITEM_COLOR[o]||[1,1,0];
      const p=.24+.10*Math.abs(Math.sin(W.t*6)); cube(0,1.5,0,p,p,p,pc);}
    if(ty==="drone_payload"&&b.payload_count>0){
      const pc=D.ITEM_COLOR[b.drone_item]||[1,1,.2];
      const p=.20+.08*Math.abs(Math.sin(W.t*5)); cube(0,1.3,0,p,p,p,pc);}
    if(D.FUEL_BURNERS[ty]&&b.fuel>0){
      const f=burnerStats(W,k).fuel_per_item;
      const g=Math.max(.15,Math.min(.6,b.fuel/f*.6)); cube(0,1.9,0,g,.2,g,[.95,.85,.2]);}
  }
  /* items */
  TA=0;
  for(const it of W.items){
    const ddx=it.x-px, ddz=it.z-pz; if(ddx*ddx+ddz*ddz>R2)continue;
    TX=0;TY=0;TZ=0;
    cube(it.x,.55,it.z,.35,.35,.35,D.ITEM_COLOR[it.type]||[.9,.9,.2]);}
  /* drones */
  for(const d of W.drones){
    const p=Math.min(1,d.prog);
    const x=d.sx+(d.tx-d.sx)*p, z=d.sz+(d.tz-d.sz)*p;
    const y=1.2+C.DRONE_LIFT_HEIGHT*Math.sin(Math.PI*p);
    TX=0;TY=0;TZ=0;
    cube(x,y,z,.32,.14,.32,[.75,.78,.82]);
    cube(x,y+.12,z,.1,.1,.1,[.2,.55,.9]);
    cube(x,y-.16,z,.18,.14,.18,D.ITEM_COLOR[d.item]||[.9,.9,.2]);}
  /* placement preview */
  if(started&&!anyMenu()){
    TX=0;TY=0;TZ=0;TA=0;
    const ok=!W.b.has(key(tgx,tgz))&&W.money>=D.BUILD_COST[sel];
    const c=ok?[.25,.95,.35]:[.95,.25,.25];
    const x0=tgx*CELL-CELL/2,x1=tgx*CELL+CELL/2,z0=tgz*CELL-CELL/2,z1=tgz*CELL+CELL/2;
    vtx(x0,.03,z0,...c);vtx(x1,.03,z0,...c);vtx(x1,.03,z1,...c);
    vtx(x0,.03,z0,...c);vtx(x1,.03,z1,...c);vtx(x0,.03,z1,...c);
    const[dx,dz]=DIRS[rotDir(snapDir(yaw),faceOff)];
    const cx=tgx*CELL, cz=tgz*CELL, s=CELL*.4, pxv=-dz, pzv=dx, w=[1,1,1];
    vtx(cx+dx*s,.05,cz+dz*s,...w);
    vtx(cx-dx*s*.35+pxv*s*.35,.05,cz-dz*s*.35+pzv*s*.35,...w);
    vtx(cx-dx*s*.35-pxv*s*.35,.05,cz-dz*s*.35-pzv*s*.35,...w);
  }
  flush(gl.TRIANGLES);

  /* HUD */
  $("h-money").textContent="$"+W.money.toLocaleString(undefined,{maximumFractionDigits:0});
  $("h-pol").textContent=W.pol.toFixed(1)+"%";
  const pb=$("h-polb"); pb.style.width=W.pol+"%";
  pb.style.background=W.pol>60?"#ff8a7a":(W.pol>25?"#ffd76e":"#8ce39a");
  $("h-pw").textContent=`${W.sup.toFixed(0)} / ${W.dem.toFixed(0)} MF`;
  const pwb=$("h-pwb"); pwb.style.width=Math.min(100,W.eff*100)+"%";
  pwb.style.background=W.eff>=.99?"#67c7ff":"#ff8a7a";
  $("h-rp").textContent=W.rp.toFixed(0);

  const aim=$("aim");
  if(started&&!anyMenu()){const info=aimInfo(W,tgx,tgz);
    if(info){aim.innerHTML=info;aim.style.display="block";}else aim.style.display="none";
  }else aim.style.display="none";
  $("cross").style.display=(started&&!anyMenu())?"block":"none";

  requestAnimationFrame(frame);
}
updateSel();
requestAnimationFrame(frame);
