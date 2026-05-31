import { useState, useEffect, useRef } from "react";
import OakwoodDads, { OwlLogo } from "./OakwoodDads";

// ── PALETTE ──────────────────────────────────────────────────────────────────
const C = {
  iron:"#232F3E", ironD:"#131A22", ironL:"#37475A",
  wheat:"#C8B896",
  white:"#FFFFFF", pageBg:"#F7F7F7", cardBg:"#FFFFFF", imgBg:"#F5F5F5",
  sage:"#3DAA6A",  sageD:"#2E8A54", sageL:"#E6F7EE",  // lighter, brighter green
  amber:"#E8973A", amberL:"#FEF3E2",                   // warm amber pop
  teal:"#1B8FA8",  tealL:"#E2F4F8",                    // teal pop for accents
  border:"#DDDDDD", borderL:"#EBEBEB",
  dark:"#111111", mid:"#555555", muted:"#767676", light:"#AAAAAA",
  green:"#007600", red:"#B12704", gold:"#C7511F",
  deal:"#CC0C39", limitedDeal:"#CC0C39",
  buyNow:"#FFA41C", buyNowD:"#FF8F00",
  addCart:"#3DAA6A", addCartD:"#2E8A54",
};

// ── ICONS ────────────────────────────────────────────────────────────────────
const Icon = ({ name, size=16, color="currentColor", sw=1.5 }) => {
  const p = { width:size, height:size, viewBox:"0 0 24 24", fill:"none", stroke:color, strokeWidth:sw, strokeLinecap:"round", strokeLinejoin:"round", style:{display:"inline-block",flexShrink:0,verticalAlign:"middle"} };
  const icons = {
    search:<svg {...p}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
    cart:<svg {...p}><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>,
    user:<svg {...p}><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
    heart:<svg {...p}><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>,
    chevR:<svg {...p}><polyline points="9 18 15 12 9 6"/></svg>,
    chevL:<svg {...p}><polyline points="15 18 9 12 15 6"/></svg>,
    star:<svg {...p} fill={color}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
    truck:<svg {...p}><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>,
    shield:<svg {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
    rotate:<svg {...p}><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>,
    check:<svg {...p}><polyline points="20 6 9 17 4 12"/></svg>,
    plus:<svg {...p}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
    minus:<svg {...p}><line x1="5" y1="12" x2="19" y2="12"/></svg>,
    trash:<svg {...p}><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>,
    tag:<svg {...p}><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>,
    bolt:<svg {...p}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
    trending:<svg {...p}><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
    percent:<svg {...p}><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>,
    box:<svg {...p}><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>,
    lock:<svg {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>,
    msg:<svg {...p}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>,
    arrowR:<svg {...p}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>,
    mail:<svg {...p}><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
    repeat:<svg {...p}><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>,
    cpu:<svg {...p}><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>,
    phone:<svg {...p}><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>,
    home2:<svg {...p}><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
    dumbbell:<svg {...p}><line x1="6.5" y1="6.5" x2="17.5" y2="17.5"/><path d="M8 8L5.5 5.5a2.83 2.83 0 000 4l1 1"/><path d="M16 16l2.5 2.5a2.83 2.83 0 000-4l-1-1"/><path d="M7.5 16.5l-2 2a2.83 2.83 0 004 0l1-1"/><path d="M16.5 7.5l2-2a2.83 2.83 0 00-4 0l-1 1"/></svg>,
    tent:<svg {...p}><path d="M3.5 21L12 3l8.5 18"/><path d="M9 21v-8l3-4 3 4v8"/></svg>,
    award:<svg {...p}><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>,
    zap:<svg {...p}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>,
    leaf:<svg {...p}><path d="M2 22c5.333-5.333 8-10.667 8-16a6 6 0 0112 0c0 5.333 2.667 10.667 8 16"/><path d="M10 6c0 5.333 2 9.333 6 12"/></svg>,
    eye:<svg {...p}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
    eyeOff:<svg {...p}><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>,
    card:<svg {...p}><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>,
    x:<svg {...p}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  };
  return icons[name] || icons.box;
};

// ── DATA ─────────────────────────────────────────────────────────────────────
const CATS=[{id:"Gadgets",icon:"cpu"},{id:"Phone",icon:"phone"},{id:"Kitchen",icon:"zap"},{id:"Beauty",icon:"award"},{id:"Pet",icon:"heart"},{id:"Car",icon:"truck"},{id:"Kids",icon:"star"},{id:"Home",icon:"home2"},{id:"Fitness",icon:"dumbbell"},{id:"Outdoor",icon:"tent"}];
const catIcon=cat=>CATS.find(c=>c.id===cat)?.icon||"box";
const NAMES=["Mini Claw Machine Desk Toy","LED Fingerprint Night Light","Magnetic Fidget Ring Set 3pk","Portable Neck Fan Hands-Free","Gua Sha Rose Quartz Tool","Eyebrow Stamp Stencil Kit","Ice Roller Face Massager","Cat Tunnel Crinkle Tube","Interactive Laser Cat Toy Auto","MagSafe Wallet Card Holder","Herb Stripper 5-Hole Stainless","Avocado Slicer 3-in-1 Tool","Corn Stripper Cob Peeler","Car Cup Holder Phone Mount","Mini Basketball Hoop Door Hanging","Stretchy Fidget Noodle 10pk","Glitter Sensory Calm Bottle DIY","LED Strip Lights USB 10ft RGB","Coiled Phone Charger Keychain","Acupressure Mat & Pillow Set","Lazy Neck Phone Stand Holder","Nail Art Stamping Kit 20pc","Blackhead Pore Strip Nose Pack","Squeaky Plush Dog Toy 3-Pack","Catnip Infused Kicker Toy","Waterproof Plasma Arc Lighter","Pop Socket Aesthetic Grip","Screen Cleaner Spray Pen","Backseat Car Hook Organizer 2pk","Glow in Dark Stars Ceiling Stickers","Infinity Cube Fidget Toy","Posture Corrector Transparent Strap","Balance Wobble Board Kids","Resistance Loop Bands 5-Pack","Clip-On Portable Sunshade","Pocket Telescopic Fishing Rod","LED Indoor Herb Garden Kit","Slow Feeder Dog Bowl Puzzle","Steering Wheel Desk Lap Tray","Car Vent Air Freshener Luxury","Sourdough Starter Kit Tools","Kids Drawing Tablet Colorful","Deep Tissue Foam Roller 18in","Gold Plant Mister Spray Bottle","Color Changing Mood Cup","Solar Powered Window Dancer","Adhesive Cable Clips Desk Organizer","USB Mini Clip Desk Fan","Heated Electric Eyelash Curler","Korean Skincare Toner Pad Set","Bamboo Cable Management Box","Wireless Charging Pad 3-in-1","Silicone Cooking Utensil Set","Blue Light Glasses Anti-Fatigue","USB Rechargeable Mini Blender","Pocket Multitool EDC Card","Reusable Silicone Food Bags 6pk","4K Dual Channel Dash Cam","3D Contoured Sleep Eye Mask","Standing Desk Converter 36in","Solar String Lights Outdoor 100ft","Beard Grooming Kit Complete","Non-Slip Yoga Mat 6mm Thick","Electric Griddle Family Size XL","Professional Knife Sharpener","Stainless Water Bottle 32oz","Full Greenhouse Grow Tent Kit","Tactical Flashlight 10000 Lumen","Portable Espresso Maker Travel","Funny Retractable Badge Reel","Stainless Steel Pet Water Fountain","Weighted Blanket 15lb King","Shower Curtain Ring Set","Compression Socks Women 6-Pack","Wall Mount Tool Organizer Panel","Microfiber Cleaning Cloths 50pk","Electric Toothbrush Replacement Heads","Kids Foam Floor Puzzle Mats","Waterproof Match Capsule EDC","Mini Projector Portable 1080p","Candle Making Starter Kit","Garlic Rocker Mincer Press","Banana Slicer Egg Cutter Combo","Collapsible Silicone Funnel Set","Magnetic Car Dashboard Mount","Dog Interactive Puzzle Toy","Ergonomic Lumbar Support Cushion","Cordless Electric Spin Scrubber","Collagen Peptides Powder 20oz","Air Fryer Silicone Liner 2pk","Reusable Produce Mesh Bags 9pk","3-Tier Bathroom Shelf Organizer","Folding Pocket EDC Knife","Digital Kitchen Scale Precise","Bamboo Drawer Organizer 6pc Set","Memory Foam Seat Cushion Coccyx","Home Gym Dumbbell Rack Stand","LED Makeup Vanity Mirror Travel","Compression Packing Cubes 6pk","Smart WiFi Plug Mini 4-Pack","Magnetic Dashboard Phone Mount","Pet Grooming Glove Brush"];
const PRICES=[9.99,11.99,8.99,12.99,9.99,8.99,11.99,11.99,12.99,12.99,7.99,8.99,6.99,12.99,12.99,5.99,8.99,11.99,11.99,14.99,13.99,12.99,7.99,9.99,8.99,12.99,8.99,7.99,8.99,8.99,7.99,12.99,13.99,9.99,14.99,13.99,14.99,13.99,14.99,9.99,14.99,13.99,12.99,13.99,10.99,6.99,8.99,11.99,13.99,11.99,12.99,12.99,9.99,9.99,11.99,9.99,9.99,14.99,12.99,14.99,13.99,12.99,9.99,14.99,14.99,14.99,13.99,12.99,7.99,13.99,14.99,12.99,9.99,12.99,9.99,11.99,13.99,12.99,6.99,13.99,9.99,8.99,9.99,12.99,8.99,12.99,11.99,13.99,14.99,12.99,9.99,11.99,12.99,13.99,13.99,9.99,12.99,11.99,13.99,11.99];
const SHIP_DAYS=["Today","Tomorrow","Wed, Apr 23","Thu, Apr 24","Fri, Apr 25","Sat, Apr 26"];

const PRODUCTS=NAMES.map((name,i)=>({
  id:i+1,name,
  category:CATS[i%CATS.length].id,
  price:PRICES[i]||9.99,
  originalPrice:+((PRICES[i]||9.99)*(1.65+Math.random()*.85)).toFixed(2),
  rating:+(3.8+Math.random()*1.1).toFixed(1),
  reviews:Math.floor(80+Math.random()*3800),
  sold:Math.floor(300+Math.random()*9000),
  limitedDeal:i%4===0,
  prime:i%3===0,
  stock:Math.floor(6+Math.random()*90),
  shipDay:SHIP_DAYS[i%SHIP_DAYS.length],
  features:["Premium quality materials","Fast 3–7 day US shipping","30-day hassle-free returns",`${Math.floor(300+Math.random()*9000).toLocaleString()} happy customers`],
}));

const disc=p=>Math.round(((p.originalPrice-p.price)/p.originalPrice)*100);

function Stars({rating,size=12,showNum=false}){
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:3}}>
      <span style={{display:"inline-flex",gap:1}}>
        {[1,2,3,4,5].map(s=><Icon key={s} name="star" size={size} color={s<=Math.round(rating)?"#FFA41C":"#DDDDDD"} sw={1}/>)}
      </span>
      {showNum&&<span style={{fontSize:size,color:"#007185",cursor:"pointer"}}>{rating}</span>}
    </span>
  );
}

function Logo({light=true}){
  const tc=light?C.white:C.dark;
  return(
    <div style={{display:"flex",alignItems:"center",gap:2,cursor:"pointer",userSelect:"none"}}>
      <span style={{fontSize:22,fontWeight:700,color:tc,lineHeight:1,letterSpacing:"-.3px"}}>L</span>
      <span style={{display:"inline-flex",gap:2,alignItems:"center",position:"relative",top:1}}>
        {[0,1].map(k=>(
          <svg key={k} width={18} height={18} viewBox="0 0 18 18">
            <circle cx={9} cy={9} r={7.5} fill="none" stroke={C.wheat} strokeWidth={2}/>
            <circle cx={9} cy={9} r={3.5} fill={C.sage}/>
            <circle cx={12} cy={6.5} r={1.2} fill={C.white} opacity=".85"/>
          </svg>
        ))}
      </span>
      <span style={{fontSize:22,fontWeight:700,color:tc,lineHeight:1,letterSpacing:"-.3px"}}>ME</span>
    </div>
  );
}

// ── TRUST BANNER ─────────────────────────────────────────────────────────────
const SLIDES=[
  {stat:"35%",headline:"LOOME shoppers save an average of 35% more",sub:"vs. Amazon, Walmart & Target — same products, better prices",icon:"percent",tag:"WHY LOOME"},
  {stat:"100+",headline:"Over 100 new trending finds added every single day",sub:"Our AI scans millions of products so you never miss a deal",icon:"trending",tag:"DAILY DROPS"},
  {stat:"FREE",headline:"Free shipping on every order, every time",sub:"No minimum. No membership. No gimmicks.",icon:"truck",tag:"FREE SHIPPING"},
  {stat:"30d",headline:"30-day free returns — no questions asked",sub:"Not happy? Full refund. No restocking fees.",icon:"rotate",tag:"BUYER GUARANTEE"},
  {stat:"$15",headline:"Every product under $15 — impulse-buy pricing",sub:"We source direct so you pay less than anywhere else.",icon:"tag",tag:"LOOME PRICING"},
];

function TrustBanner(){
  const [active,setActive]=useState(0);
  const [show,setShow]=useState(true);
  const t=useRef(null);

  const goTo=(i)=>{setShow(false);setTimeout(()=>{setActive(i);setShow(true);},200);};
  useEffect(()=>{
    t.current=setInterval(()=>{setShow(false);setTimeout(()=>{setActive(a=>(a+1)%SLIDES.length);setShow(true);},200);},4500);
    return()=>clearInterval(t.current);
  },[]);

  const s=SLIDES[active];
  // Color pop per slide: alternates amber, teal, sage
  const pops=[C.amber,C.teal,C.sage,C.amber,C.teal];
  const pop=pops[active];
  return(
    <div style={{background:C.iron,borderTop:`3px solid ${C.wheat}`,borderBottom:`3px solid ${C.wheat}`,padding:"0 20px"}}>
      <div style={{maxWidth:1380,margin:"0 auto",display:"flex",alignItems:"center",gap:0,height:102}}>
        <button onClick={()=>goTo((active-1+SLIDES.length)%SLIDES.length)} style={{background:"none",border:"none",cursor:"pointer",padding:"0 12px 0 0",color:"rgba(255,255,255,.35)",display:"flex",alignItems:"center",flexShrink:0,transition:"color .15s"}}
          onMouseEnter={e=>e.currentTarget.style.color="rgba(255,255,255,.8)"}
          onMouseLeave={e=>e.currentTarget.style.color="rgba(255,255,255,.35)"}>
          <Icon name="chevL" size={18} color="currentColor" sw={2.2}/>
        </button>

        <div style={{flex:1,display:"flex",alignItems:"center",gap:20,opacity:show?1:0,transition:"opacity .2s ease"}}>
          {/* Icon + stat with color pop */}
          <div style={{display:"flex",alignItems:"center",gap:12,flexShrink:0}}>
            <div style={{width:48,height:48,borderRadius:"50%",background:`${pop}22`,border:`1.5px solid ${pop}60`,display:"flex",alignItems:"center",justifyContent:"center"}}>
              <Icon name={s.icon} size={22} color={pop} sw={1.8}/>
            </div>
            <div style={{fontSize:32,fontWeight:800,color:pop,letterSpacing:"-.5px",minWidth:60,lineHeight:1}}>{s.stat}</div>
          </div>

          <div style={{width:1,height:48,background:"rgba(255,255,255,.12)",flexShrink:0}}/>

          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
              <span style={{fontSize:9,fontWeight:700,letterSpacing:".13em",color:pop,background:`${pop}20`,padding:"2px 9px",borderRadius:3,border:`1px solid ${pop}40`}}>{s.tag}</span>
            </div>
            <div style={{fontSize:15,fontWeight:700,color:C.white,lineHeight:1.3,marginBottom:2}}>{s.headline}</div>
            <div style={{fontSize:11,color:"rgba(255,255,255,.48)"}}>{s.sub}</div>
          </div>
        </div>

        <button onClick={()=>goTo((active+1)%SLIDES.length)} style={{background:"none",border:"none",cursor:"pointer",padding:"0 0 0 12px",color:"rgba(255,255,255,.35)",display:"flex",alignItems:"center",flexShrink:0,transition:"color .15s"}}
          onMouseEnter={e=>e.currentTarget.style.color="rgba(255,255,255,.8)"}
          onMouseLeave={e=>e.currentTarget.style.color="rgba(255,255,255,.35)"}>
          <Icon name="chevR" size={18} color="currentColor" sw={2.2}/>
        </button>

        <div style={{display:"flex",gap:5,flexShrink:0,marginLeft:8}}>
          {SLIDES.map((_,i)=>(
            <button key={i} onClick={()=>goTo(i)} style={{width:i===active?22:7,height:7,borderRadius:4,background:i===active?pop:"rgba(255,255,255,.2)",border:"none",cursor:"pointer",padding:0,transition:"width .28s,background .28s"}}/>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── BUY NOW MODAL ─────────────────────────────────────────────────────────────
function BuyNowModal({product,user,setUser,onClose,setPage}){
  const [step,setStep]=useState(user?.cards?.length?"select":"enter");
  const [selCard,setSelCard]=useState(user?.cards?.[0]||null);
  const [newCard,setNewCard]=useState({num:"",exp:"",cvv:"",name:""});
  const [save,setSave]=useState(true);
  const [done,setDone]=useState(false);
  const [addr,setAddr]=useState(user?.addresses?.[0]||{name:"",street:"",city:"",zip:""});

  const place=()=>{
    if(save&&newCard.num&&user){
      const masked="•••• •••• •••• "+newCard.num.replace(/\s/g,"").slice(-4);
      setUser(u=>({...u,cards:[...(u.cards||[]),{masked,exp:newCard.exp,id:Date.now()}]}));
    }
    if(user&&addr.street){
      setUser(u=>({...u,addresses:[addr,...(u.addresses||[]).filter(a=>a.street!==addr.street)]}));
    }
    setDone(true);
  };

  const Field=({label,k,ph,half,type="text"})=>(
    <div style={{flex:half?"1":"unset",marginBottom:10}}>
      <div style={{fontSize:11,color:C.mid,marginBottom:3,fontWeight:500}}>{label}</div>
      <input value={k.includes(".")?newCard[k.split(".")[1]]:addr[k]} type={type}
        onChange={e=>{
          if(k.startsWith("card.")){setNewCard(x=>({...x,[k.split(".")[1]]:e.target.value}));}
          else{setAddr(x=>({...x,[k]:e.target.value}));}
        }}
        placeholder={ph} style={{width:"100%",padding:"8px 10px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:13,outline:"none",transition:"border-color .15s"}}
        onFocus={e=>e.target.style.borderColor=C.sage} onBlur={e=>e.target.style.borderColor=C.border}/>
    </div>
  );

  return(
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.65)",zIndex:9000,display:"flex",alignItems:"center",justifyContent:"center",padding:20}}>
      <div style={{background:C.white,borderRadius:10,width:"100%",maxWidth:480,maxHeight:"90vh",overflow:"auto",boxShadow:"0 20px 60px rgba(0,0,0,.3)"}}>
        {/* Header */}
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"16px 20px",borderBottom:`1px solid ${C.borderL}`}}>
          <div style={{fontSize:16,fontWeight:700,color:C.dark}}>Buy Now</div>
          <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer",color:C.muted,display:"flex",alignItems:"center"}}>
            <Icon name="x" size={20} color={C.muted} sw={2}/>
          </button>
        </div>

        {done?(
          <div style={{padding:32,textAlign:"center"}}>
            <div style={{width:56,height:56,borderRadius:"50%",background:C.sageL,display:"flex",alignItems:"center",justifyContent:"center",margin:"0 auto 14px"}}>
              <Icon name="check" size={28} color={C.sage} sw={2.5}/>
            </div>
            <div style={{fontSize:18,fontWeight:700,color:C.dark,marginBottom:6}}>Order Placed!</div>
            <div style={{fontSize:13,color:C.mid,marginBottom:6}}>
              <strong>{product.name}</strong>
            </div>
            <div style={{fontSize:22,fontWeight:700,color:C.dark,marginBottom:4}}>${product.price}</div>
            <div style={{fontSize:12,color:C.green,marginBottom:20}}>FREE delivery · {product.shipDay}</div>
            <button onClick={onClose} style={{padding:"10px 24px",background:C.sage,border:"none",borderRadius:20,color:C.white,fontWeight:700,cursor:"pointer",fontSize:13}}>
              Continue Shopping
            </button>
          </div>
        ):(
          <div style={{padding:20}}>
            {/* Product preview */}
            <div style={{display:"flex",gap:12,padding:14,background:C.pageBg,borderRadius:8,marginBottom:18,border:`1px solid ${C.borderL}`}}>
              <div style={{width:60,height:60,background:C.imgBg,borderRadius:6,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>
                <Icon name={catIcon(product.category)} size={28} color={C.mid} sw={1.3}/>
              </div>
              <div style={{flex:1}}>
                <div style={{fontSize:13,fontWeight:600,color:C.dark,lineHeight:1.3,marginBottom:4}}>{product.name}</div>
                <div style={{fontSize:11,color:C.green}}>In Stock · FREE delivery {product.shipDay}</div>
              </div>
              <div style={{fontSize:18,fontWeight:800,color:C.dark,flexShrink:0}}>${product.price}</div>
            </div>

            {/* Shipping address */}
            <div style={{marginBottom:18}}>
              <div style={{fontSize:13,fontWeight:700,color:C.dark,marginBottom:10}}>Ship to</div>
              {user?.addresses?.length>0&&(
                <div style={{marginBottom:10}}>
                  {user.addresses.map((a,i)=>(
                    <div key={i} onClick={()=>setAddr(a)} style={{padding:"8px 12px",border:`1px solid ${JSON.stringify(addr)===JSON.stringify(a)?C.sage:C.border}`,borderRadius:5,marginBottom:6,cursor:"pointer",fontSize:12,color:C.dark,background:JSON.stringify(addr)===JSON.stringify(a)?C.sageL:C.white}}>
                      {a.name} · {a.street}, {a.city} {a.zip}
                    </div>
                  ))}
                  <button onClick={()=>setAddr({name:"",street:"",city:"",zip:""})} style={{fontSize:12,color:C.sage,background:"none",border:"none",cursor:"pointer",padding:0}}>+ New address</button>
                </div>
              )}
              {(!user?.addresses?.length||!addr.street)&&(
                <div>
                  <Field label="Full Name" k="name" ph="Your name"/>
                  <Field label="Street Address" k="street" ph="123 Main Street"/>
                  <div style={{display:"flex",gap:10}}>
                    <Field label="City" k="city" ph="City" half/>
                    <Field label="ZIP" k="zip" ph="90210" half/>
                  </div>
                </div>
              )}
            </div>

            {/* Payment */}
            <div style={{marginBottom:18}}>
              <div style={{fontSize:13,fontWeight:700,color:C.dark,marginBottom:10}}>Payment</div>
              {step==="select"&&user?.cards?.length>0&&(
                <div>
                  {user.cards.map((card,i)=>(
                    <div key={i} onClick={()=>setSelCard(card)} style={{padding:"10px 12px",border:`1px solid ${selCard?.id===card.id?C.sage:C.border}`,borderRadius:5,marginBottom:6,cursor:"pointer",display:"flex",alignItems:"center",gap:10,background:selCard?.id===card.id?C.sageL:C.white}}>
                      <Icon name="card" size={18} color={selCard?.id===card.id?C.sage:C.mid} sw={1.5}/>
                      <div style={{flex:1}}>
                        <div style={{fontSize:13,fontWeight:600,color:C.dark}}>{card.masked}</div>
                        <div style={{fontSize:11,color:C.muted}}>Expires {card.exp}</div>
                      </div>
                      {selCard?.id===card.id&&<Icon name="check" size={14} color={C.sage} sw={2.5}/>}
                    </div>
                  ))}
                  <button onClick={()=>setStep("enter")} style={{fontSize:12,color:C.sage,background:"none",border:"none",cursor:"pointer",padding:0}}>+ Use a different card</button>
                </div>
              )}
              {step==="enter"&&(
                <div>
                  <Field label="Card Number" k="card.num" ph="1234 5678 9012 3456"/>
                  <div style={{display:"flex",gap:10}}>
                    <Field label="Expiry (MM/YY)" k="card.exp" ph="12/27" half/>
                    <Field label="CVV" k="card.cvv" ph="•••" half type="password"/>
                  </div>
                  <Field label="Name on Card" k="card.name" ph="Your name"/>
                  {user&&<label style={{display:"flex",alignItems:"center",gap:7,fontSize:12,color:C.mid,cursor:"pointer",marginBottom:6}}>
                    <input type="checkbox" checked={save} onChange={e=>setSave(e.target.checked)} style={{accentColor:C.sage}}/>
                    Save card to my account
                  </label>}
                </div>
              )}
            </div>

            {/* Order summary */}
            <div style={{background:C.pageBg,borderRadius:6,padding:12,marginBottom:16,border:`1px solid ${C.borderL}`}}>
              {[["Item","$"+product.price],["Shipping","FREE"],["Tax","Included"],].map(([l,v])=>(
                <div key={l} style={{display:"flex",justifyContent:"space-between",fontSize:12,marginBottom:5}}>
                  <span style={{color:C.muted}}>{l}</span><span style={{fontWeight:v==="FREE"?600:400,color:v==="FREE"?C.green:C.dark}}>{v}</span>
                </div>
              ))}
              <div style={{height:1,background:C.border,margin:"8px 0"}}/>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:15,fontWeight:800,color:C.dark}}>
                <span>Order Total</span><span>${product.price}</span>
              </div>
            </div>

            <button onClick={place} style={{width:"100%",padding:"13px",background:C.buyNow,border:"none",borderRadius:24,fontWeight:800,cursor:"pointer",fontSize:14,color:C.dark,boxShadow:"0 2px 8px rgba(255,164,28,.4)"}}>
              Place Order — ${product.price}
            </button>
            <div style={{fontSize:10,color:C.muted,textAlign:"center",marginTop:8}}>
              By placing your order, you agree to LOOME's Terms & Privacy Policy.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── LOGIN MODAL ───────────────────────────────────────────────────────────────
function LoginModal({onClose,setUser,setToast}){
  const [mode,setMode]=useState("signin");
  const [f,setF]=useState({email:"",pass:"",name:""});
  const [show,setShow]=useState(false);
  const upd=(k,v)=>setF(x=>({...x,[k]:v}));

  const submit=()=>{
    if(mode==="signin"){
      const stored=JSON.parse(localStorage.getItem("loome_user")||"null");
      if(stored&&stored.email===f.email){setUser(stored);onClose();setToast("Welcome back, "+stored.name+"!");}
      else{setToast("Account not found. Please sign up.");}
    } else {
      const u={id:Date.now(),name:f.name,email:f.email,pass:f.pass,cards:[],addresses:[],orders:[],wishlist:[]};
      localStorage.setItem("loome_user",JSON.stringify(u));
      setUser(u);onClose();setToast("Account created! Welcome to LOOME.");
    }
  };

  return(
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.6)",zIndex:9000,display:"flex",alignItems:"center",justifyContent:"center",padding:20}}>
      <div style={{background:C.white,borderRadius:10,width:"100%",maxWidth:380,padding:28,boxShadow:"0 20px 60px rgba(0,0,0,.25)"}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}>
          <Logo light={false}/>
          <button onClick={onClose} style={{background:"none",border:"none",cursor:"pointer"}}><Icon name="x" size={18} color={C.muted} sw={2}/></button>
        </div>
        <div style={{fontSize:18,fontWeight:700,color:C.dark,marginBottom:4}}>{mode==="signin"?"Sign in":"Create account"}</div>
        <div style={{fontSize:12,color:C.muted,marginBottom:20}}>{mode==="signin"?"Welcome back to LOOME":"Start finding deals before everyone else"}</div>

        {mode==="signup"&&(
          <div style={{marginBottom:12}}>
            <div style={{fontSize:11,fontWeight:500,color:C.mid,marginBottom:3}}>Full Name</div>
            <input value={f.name} onChange={e=>upd("name",e.target.value)} placeholder="Your name"
              style={{width:"100%",padding:"9px 11px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:13,outline:"none"}}
              onFocus={e=>e.target.style.borderColor=C.sage} onBlur={e=>e.target.style.borderColor=C.border}/>
          </div>
        )}
        <div style={{marginBottom:12}}>
          <div style={{fontSize:11,fontWeight:500,color:C.mid,marginBottom:3}}>Email</div>
          <input value={f.email} onChange={e=>upd("email",e.target.value)} placeholder="you@email.com" type="email"
            style={{width:"100%",padding:"9px 11px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:13,outline:"none"}}
            onFocus={e=>e.target.style.borderColor=C.sage} onBlur={e=>e.target.style.borderColor=C.border}/>
        </div>
        <div style={{marginBottom:20}}>
          <div style={{fontSize:11,fontWeight:500,color:C.mid,marginBottom:3}}>Password</div>
          <div style={{position:"relative"}}>
            <input value={f.pass} onChange={e=>upd("pass",e.target.value)} placeholder="••••••••" type={show?"text":"password"}
              style={{width:"100%",padding:"9px 36px 9px 11px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:13,outline:"none"}}
              onFocus={e=>e.target.style.borderColor=C.sage} onBlur={e=>e.target.style.borderColor=C.border}/>
            <button onClick={()=>setShow(s=>!s)} style={{position:"absolute",right:10,top:"50%",transform:"translateY(-50%)",background:"none",border:"none",cursor:"pointer",color:C.muted}}>
              <Icon name={show?"eyeOff":"eye"} size={15} color={C.muted} sw={1.8}/>
            </button>
          </div>
        </div>
        <button onClick={submit} style={{width:"100%",padding:"12px",background:C.sage,border:"none",borderRadius:6,color:C.white,fontWeight:700,cursor:"pointer",fontSize:14,marginBottom:14}}>
          {mode==="signin"?"Sign In":"Create Account"}
        </button>
        <div style={{textAlign:"center",fontSize:12,color:C.mid}}>
          {mode==="signin"?"Don't have an account? ":"Already have an account? "}
          <span onClick={()=>setMode(mode==="signin"?"signup":"signin")} style={{color:C.sage,cursor:"pointer",fontWeight:600}}>
            {mode==="signin"?"Create one":"Sign in"}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── HEADER ────────────────────────────────────────────────────────────────────
function Header({cart,nav,setSearch,setCat,user,setShowLogin,setUser}){
  const [q,setQ]=useState("");
  const total=cart.reduce((s,i)=>s+i.qty,0);
  const signOut=()=>{setUser(null);localStorage.removeItem("loome_user");};
  return(
    <div style={{background:C.iron,position:"sticky",top:0,zIndex:900,boxShadow:"0 2px 8px rgba(0,0,0,.2)"}}>
      <div style={{maxWidth:1380,margin:"0 auto",display:"flex",alignItems:"center",gap:14,height:58,padding:"0 16px"}}>
        <div onClick={()=>nav("home")}><Logo/></div>
        <select onChange={e=>{setCat(e.target.value);nav("home");}} style={{padding:"6px 9px",background:"rgba(255,255,255,.1)",border:"1px solid rgba(255,255,255,.2)",borderRadius:4,color:C.white,fontSize:11,cursor:"pointer",flexShrink:0}}>
          <option value="All">All Departments</option>
          {CATS.map(c=><option key={c.id} value={c.id}>{c.id}</option>)}
        </select>
        <form onSubmit={e=>{e.preventDefault();setSearch(q);nav("home");}} style={{flex:1,display:"flex",maxWidth:600}}>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search LOOME finds..."
            style={{flex:1,padding:"9px 14px",border:"none",borderRadius:"4px 0 0 4px",fontSize:13,outline:"none",background:C.white,color:C.dark}}/>
          <button type="submit" style={{padding:"9px 14px",background:C.sage,border:"none",borderRadius:"0 4px 4px 0",color:C.white,cursor:"pointer",display:"flex",alignItems:"center"}}>
            <Icon name="search" size={16} color={C.white} sw={2.2}/>
          </button>
        </form>
        <div style={{display:"flex",gap:6,marginLeft:"auto",flexShrink:0,alignItems:"center"}}>
          <button onClick={()=>nav("dads")} title="2038 Oakwood Dads" style={{display:"flex",flexDirection:"column",alignItems:"center",gap:1,background:"transparent",border:"none",color:C.white,cursor:"pointer",padding:"4px 8px",borderRadius:4,fontSize:10}}>
            <OwlLogo size={20}/>
            <span style={{fontWeight:600,letterSpacing:".06em"}}>Dads</span>
          </button>
          {user?(
            <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:0}}>
              <span style={{fontSize:10,color:"rgba(255,255,255,.7)"}}>Hello, {user.name.split(" ")[0]}</span>
              <div style={{display:"flex",gap:8}}>
                <span onClick={()=>nav("account")} style={{fontSize:11,color:C.white,cursor:"pointer",fontWeight:600}}>Account & Lists</span>
                <span style={{color:"rgba(255,255,255,.3)"}}>|</span>
                <span onClick={signOut} style={{fontSize:11,color:"rgba(255,255,255,.6)",cursor:"pointer"}}>Sign out</span>
              </div>
            </div>
          ):(
            <button onClick={()=>setShowLogin(true)} style={{display:"flex",flexDirection:"column",alignItems:"center",gap:1,background:"transparent",border:"none",color:C.white,cursor:"pointer",padding:"4px 8px",borderRadius:4,fontSize:10}}>
              <Icon name="user" size={17} color={C.white} sw={1.5}/>
              <span>Sign In</span>
            </button>
          )}
          <button onClick={()=>nav("cart")} style={{display:"flex",flexDirection:"column",alignItems:"center",gap:1,background:"transparent",border:"none",color:C.white,cursor:"pointer",padding:"4px 8px",borderRadius:4,fontSize:10,position:"relative"}}>
            <Icon name="cart" size={17} color={C.white} sw={1.5}/>
            <span>Cart{total>0?` (${total})`:""}</span>
            {total>0&&<span style={{position:"absolute",top:0,right:0,background:C.sage,color:C.white,borderRadius:"50%",width:16,height:16,fontSize:9,display:"flex",alignItems:"center",justifyContent:"center",fontWeight:700}}>{total}</span>}
          </button>
        </div>
      </div>
      <div style={{background:C.ironL,padding:"0 16px"}}>
        <div style={{maxWidth:1380,margin:"0 auto",display:"flex",height:32,overflowX:"auto",gap:0}}>
          {["Today's Deals","Under $10","New Arrivals","Subscribe & Save",...CATS.map(c=>c.id)].map((c,i)=>(
            <button key={c} onClick={()=>{setCat(i<4?"All":c);nav("home");}} style={{padding:"0 13px",background:"transparent",border:"none",borderBottom:"2px solid transparent",color:"rgba(255,255,255,.7)",cursor:"pointer",fontSize:11,height:"100%",whiteSpace:"nowrap",transition:"all .15s",fontWeight:i<4?600:400}}
              onMouseEnter={e=>{e.currentTarget.style.color=C.white;e.currentTarget.style.borderBottomColor=C.white;}}
              onMouseLeave={e=>{e.currentTarget.style.color="rgba(255,255,255,.7)";e.currentTarget.style.borderBottomColor="transparent";}}>
              {c}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── PRODUCT CARD ──────────────────────────────────────────────────────────────
function ProductCard({p,nav,addToCart,user,setShowLogin,setBuyNowProduct}){
  const [addedMsg,setAddedMsg]=useState("");
  const d=disc(p);
  const handleAdd=(e)=>{e.stopPropagation();addToCart(p);setAddedMsg("Added");setTimeout(()=>setAddedMsg(""),1600);};
  const handleBuyNow=(e)=>{e.stopPropagation();if(!user){setShowLogin(true);return;}setBuyNowProduct(p);};
  return(
    <div style={{background:C.white,borderRadius:6,border:`1px solid ${C.border}`,overflow:"hidden",display:"flex",flexDirection:"column",boxShadow:"0 1px 3px rgba(0,0,0,.06)",cursor:"pointer",transition:"box-shadow .18s,transform .18s"}} onClick={()=>nav(`product:${p.id}`)}
      onMouseEnter={e=>{e.currentTarget.style.boxShadow="0 4px 16px rgba(0,0,0,.12)";e.currentTarget.style.transform="translateY(-1px)";}}
      onMouseLeave={e=>{e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,.06)";e.currentTarget.style.transform="translateY(0)";}}>

      {/* Image area — pure white/gray, no color tints */}
      <div style={{position:"relative"}}>
        {p.limitedDeal&&<div style={{position:"absolute",top:0,left:0,right:0,background:C.limitedDeal,color:C.white,fontSize:10,fontWeight:700,padding:"3px 0",textAlign:"center",zIndex:2,letterSpacing:".03em"}}>Limited time deal</div>}
        <div style={{background:C.imgBg,height:160,display:"flex",alignItems:"center",justifyContent:"center",borderBottom:`1px solid ${C.borderL}`,marginTop:p.limitedDeal?22:0}}>
          <Icon name={catIcon(p.category)} size={56} color="#AAAAAA" sw={1}/>
        </div>
      </div>

      <div style={{padding:"10px 12px 12px",flex:1,display:"flex",flexDirection:"column",gap:4}}>
        <div style={{fontSize:13,fontWeight:400,color:C.dark,lineHeight:1.4,display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical",overflow:"hidden",minHeight:36}}>{p.name}</div>
        <div style={{display:"flex",alignItems:"center",gap:5}}>
          <Stars rating={p.rating} size={12}/>
          <span style={{fontSize:11,color:"#007185"}}>{p.reviews.toLocaleString()}</span>
        </div>
        <div style={{fontSize:10,color:C.green,fontWeight:500}}>{p.sold.toLocaleString()}+ bought in past month</div>

        {/* Price */}
        <div style={{marginTop:2}}>
          {p.limitedDeal&&<div style={{display:"inline-block",fontSize:10,color:C.white,fontWeight:700,background:C.limitedDeal,padding:"1px 7px",borderRadius:3,marginBottom:3}}>Limited time deal</div>}
          <div style={{display:"flex",alignItems:"baseline",gap:5}}>
            <span style={{fontSize:11,color:C.dark,verticalAlign:"top",marginTop:2}}>$</span>
            <span style={{fontSize:20,fontWeight:700,color:C.dark,lineHeight:1}}>{p.price.toString().split(".")[0]}</span>
            <span style={{fontSize:12,color:C.dark,verticalAlign:"super"}}>{(p.price%1).toFixed(2).slice(1)}</span>
            {d>0&&<span style={{fontSize:10,color:C.limitedDeal,marginLeft:4}}>({d}% off)</span>}
          </div>
          <div style={{fontSize:10,color:C.muted}}>List: <span style={{textDecoration:"line-through"}}>${p.originalPrice}</span></div>
        </div>

        {/* Shipping — teal pop */}
        <div style={{fontSize:11,color:C.dark,display:"flex",alignItems:"center",gap:4}}>
          {p.prime?<>
            <Icon name="truck" size={11} color={C.teal} sw={2}/>
            <span style={{color:C.teal,fontWeight:600}}>FREE</span>
            <span> delivery </span><strong>{p.shipDay}</strong>
          </>:<span style={{color:C.muted}}>Ships {p.shipDay}</span>}
        </div>

        {/* Category tag — amber pop */}
        <div style={{display:"inline-flex",alignItems:"center",gap:4}}>
          <span style={{fontSize:9,fontWeight:600,color:C.amber,background:C.amberL,padding:"1px 7px",borderRadius:3,border:`1px solid ${C.amber}40`}}>{p.category}</span>
        </div>

        {/* Buttons */}
        <div style={{display:"flex",gap:6,marginTop:4}} onClick={e=>e.stopPropagation()}>
          <button onClick={handleAdd} style={{flex:1,padding:"7px 4px",background:addedMsg?C.sageD:C.addCart,border:"none",borderRadius:20,color:C.white,fontWeight:600,cursor:"pointer",fontSize:11,transition:"background .18s",display:"flex",alignItems:"center",justifyContent:"center",gap:3}}>
            {addedMsg?<><Icon name="check" size={11} color={C.white} sw={2.5}/>Added</>:"Add to Cart"}
          </button>
          <button onClick={handleBuyNow} style={{flex:1,padding:"7px 4px",background:C.buyNow,border:"none",borderRadius:20,color:C.dark,fontWeight:700,cursor:"pointer",fontSize:11,display:"flex",alignItems:"center",justifyContent:"center",boxShadow:"0 2px 6px rgba(255,164,28,.3)"}}>
            Buy Now
          </button>
        </div>
      </div>
    </div>
  );
}

// ── HOME ──────────────────────────────────────────────────────────────────────
function Home({nav,addToCart,cat,search,user,setShowLogin,setBuyNowProduct}){
  const [sort,setSort]=useState("trending");
  let prods=[...PRODUCTS];
  if(cat&&cat!=="All") prods=prods.filter(p=>p.category===cat);
  if(search) prods=prods.filter(p=>p.name.toLowerCase().includes(search.toLowerCase()));
  if(sort==="price_low") prods.sort((a,b)=>a.price-b.price);
  if(sort==="price_high") prods.sort((a,b)=>b.price-a.price);
  if(sort==="rating") prods.sort((a,b)=>b.rating-a.rating);
  if(sort==="reviews") prods.sort((a,b)=>b.reviews-a.reviews);

  return(
    <div style={{width:"100%",display:"flex",justifyContent:"center",background:C.pageBg}}>
    <div style={{width:"100%",maxWidth:1380,padding:"16px"}}>
      {/* Deals strip */}
      {!cat||cat==="All"?<div style={{background:C.white,borderRadius:8,padding:"14px 16px",marginBottom:16,border:`1px solid ${C.border}`}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div style={{fontSize:18,fontWeight:700,color:C.dark}}>Today's Deals</div>
          <span onClick={()=>nav("home")} style={{fontSize:13,color:"#007185",cursor:"pointer"}}>See all deals</span>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(130px,1fr))",gap:10}}>
          {PRODUCTS.filter(p=>p.limitedDeal).slice(0,8).map(p=>(
            <div key={p.id} onClick={()=>nav(`product:${p.id}`)} style={{cursor:"pointer",textAlign:"center",padding:10,borderRadius:6,border:`1px solid ${C.borderL}`,transition:"box-shadow .15s"}}
              onMouseEnter={e=>e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,.1)"}
              onMouseLeave={e=>e.currentTarget.style.boxShadow="none"}>
              <div style={{background:C.imgBg,borderRadius:6,height:80,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:7}}>
                <Icon name={catIcon(p.category)} size={36} color="#AAAAAA" sw={1}/>
              </div>
              <div style={{fontSize:11,color:C.limitedDeal,fontWeight:700}}>Up to {disc(p)}% off</div>
              <div style={{fontSize:10,color:C.muted,marginTop:2}}>{p.category}</div>
            </div>
          ))}
        </div>
      </div>:null}

      {/* Sort + results */}
      <div style={{display:"flex",alignItems:"center",marginBottom:12,gap:10}}>
        <div style={{fontSize:15,fontWeight:700,color:C.dark}}>
          {search?`Results for "${search}"`:cat==="All"?"Top 100 Trending Finds":cat}
          <span style={{fontSize:12,color:C.muted,fontWeight:400,marginLeft:6}}>({prods.length} results)</span>
        </div>
        <div style={{marginLeft:"auto",display:"flex",gap:8,alignItems:"center"}}>
          <span style={{fontSize:12,color:C.mid}}>Sort by:</span>
          <select value={sort} onChange={e=>setSort(e.target.value)} style={{padding:"5px 9px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:12,background:C.white,color:C.dark}}>
            <option value="trending">Featured</option>
            <option value="price_low">Price: Low to High</option>
            <option value="price_high">Price: High to Low</option>
            <option value="rating">Avg. Customer Review</option>
            <option value="reviews">Most Reviews</option>
          </select>
        </div>
      </div>

      {prods.length===0?(
        <div style={{textAlign:"center",padding:60,background:C.white,borderRadius:8,border:`1px solid ${C.border}`}}>
          <div style={{fontSize:14,color:C.muted,marginBottom:12}}>No results for "{search}"</div>
          <button onClick={()=>nav("home")} style={{padding:"8px 20px",background:C.sage,border:"none",borderRadius:4,color:C.white,fontWeight:600,cursor:"pointer",fontSize:13}}>Browse all products</button>
        </div>
      ):(
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(192px,1fr))",gap:14}}>
          {prods.map((p,i)=>(
            <div key={p.id} style={{opacity:0,animation:`fadeUp .25s ease ${Math.min(i,20)*.022}s forwards`}}>
              <ProductCard p={p} nav={nav} addToCart={addToCart} user={user} setShowLogin={setShowLogin} setBuyNowProduct={setBuyNowProduct}/>
            </div>
          ))}
        </div>
      )}
    </div>
    </div>
  );
}

// ── PRODUCT DETAIL ────────────────────────────────────────────────────────────
function ProductDetail({id,nav,addToCart,user,setShowLogin,setBuyNowProduct}){
  const p=PRODUCTS.find(x=>x.id===id);
  const [qty,setQty]=useState(1);
  const [tab,setTab]=useState("about");
  const [added,setAdded]=useState(false);
  const related=PRODUCTS.filter(x=>x.category===p.category&&x.id!==p.id).slice(0,6);
  const d=disc(p);
  const doAdd=()=>{for(let i=0;i<qty;i++) addToCart(p);setAdded(true);setTimeout(()=>setAdded(false),2000);};
  const doBuyNow=()=>{if(!user){setShowLogin(true);return;}setBuyNowProduct(p);};

  return(
    <div style={{background:C.white,minHeight:"100vh",width:"100%",display:"flex",justifyContent:"center"}}>
      <div style={{width:"100%",maxWidth:1380,padding:"14px 16px"}}>
        {/* Breadcrumb */}
        <div style={{display:"flex",gap:5,fontSize:12,color:"#007185",marginBottom:14,alignItems:"center"}}>
          <span onClick={()=>nav("home")} style={{cursor:"pointer"}}>LOOME</span>
          <Icon name="chevR" size={10} color={C.light} sw={2}/>
          <span onClick={()=>nav("home")} style={{cursor:"pointer"}}>{p.category}</span>
          <Icon name="chevR" size={10} color={C.light} sw={2}/>
          <span style={{color:C.muted,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",maxWidth:300}}>{p.name}</span>
        </div>

        <div style={{display:"grid",gridTemplateColumns:"360px 1fr 240px",gap:24}}>
          {/* Image */}
          <div>
            <div style={{background:C.imgBg,borderRadius:8,height:340,display:"flex",alignItems:"center",justifyContent:"center",border:`1px solid ${C.border}`,marginBottom:10}}>
              <Icon name={catIcon(p.category)} size={120} color="#CCCCCC" sw={.8}/>
            </div>
            <div style={{display:"flex",gap:8}}>
              {[0,1,2,3].map(i=>(
                <div key={i} style={{flex:1,background:C.imgBg,borderRadius:5,height:60,display:"flex",alignItems:"center",justifyContent:"center",border:`2px solid ${i===0?C.sage:C.border}`,cursor:"pointer"}}>
                  <Icon name={catIcon(p.category)} size={22} color="#BBBBBB" sw={1}/>
                </div>
              ))}
            </div>
          </div>

          {/* Info */}
          <div>
            {p.limitedDeal&&<div style={{background:C.limitedDeal,color:C.white,fontSize:11,fontWeight:700,padding:"3px 10px",borderRadius:3,display:"inline-block",marginBottom:8}}>Limited time deal</div>}
            <h1 style={{fontSize:20,fontWeight:700,color:C.dark,lineHeight:1.3,marginBottom:10}}>{p.name}</h1>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
              <Stars rating={p.rating} size={14} showNum/>
              <span style={{fontSize:13,color:"#007185",cursor:"pointer"}}>{p.reviews.toLocaleString()} ratings</span>
              <span style={{color:C.borderL}}>|</span>
              <span style={{fontSize:12,color:C.green,fontWeight:600}}>{p.sold.toLocaleString()}+ bought in past month</span>
            </div>
            <div style={{height:1,background:C.borderL,marginBottom:14}}/>

            {/* Price */}
            <div style={{marginBottom:14}}>
              {p.limitedDeal&&<div style={{fontSize:12,color:C.limitedDeal,fontWeight:600,marginBottom:4}}>Limited time deal</div>}
              <div style={{display:"flex",alignItems:"baseline",gap:4,marginBottom:4}}>
                <span style={{fontSize:13,color:C.dark}}>-{d}%</span>
                <span style={{fontSize:13,color:C.dark,verticalAlign:"top",marginTop:1}}>$</span>
                <span style={{fontSize:32,fontWeight:800,color:C.dark,lineHeight:1}}>{p.price.toString().split(".")[0]}</span>
                <span style={{fontSize:14,color:C.dark,verticalAlign:"super"}}>{(p.price%1).toFixed(2).slice(1)}</span>
              </div>
              <div style={{fontSize:12,color:C.muted}}>List Price: <span style={{textDecoration:"line-through"}}>${p.originalPrice}</span></div>
              <div style={{fontSize:12,color:C.muted,marginTop:3}}>Includes tax · FREE Returns</div>
            </div>

            {/* Subscribe */}
            <div style={{background:"#F0FDF4",border:"1px solid #BBF7D0",borderRadius:6,padding:12,marginBottom:14}}>
              <div style={{fontSize:13,fontWeight:700,color:C.green,marginBottom:3}}>Subscribe & Save — 10% off</div>
              <div style={{fontSize:12,color:C.mid}}>Auto-delivers at <strong>${(p.price*.9).toFixed(2)}</strong>/month · Free shipping · Cancel anytime</div>
            </div>

            {/* Features */}
            <div style={{marginBottom:14}}>
              <div style={{fontSize:14,fontWeight:700,color:C.dark,marginBottom:8}}>About this item</div>
              {p.features.map((f,i)=>(
                <div key={i} style={{display:"flex",gap:8,fontSize:13,color:C.mid,marginBottom:6,alignItems:"flex-start"}}>
                  <span style={{color:C.sage,flexShrink:0,marginTop:2}}>›</span>{f}
                </div>
              ))}
            </div>

            {/* Tabs */}
            <div style={{borderTop:`1px solid ${C.borderL}`,paddingTop:14}}>
              <div style={{display:"flex",gap:0,borderBottom:`1px solid ${C.borderL}`,marginBottom:14}}>
                {["about","reviews","shipping"].map(t=>(
                  <button key={t} onClick={()=>setTab(t)} style={{padding:"8px 16px",background:"none",border:"none",borderBottom:`3px solid ${tab===t?C.sage:"transparent"}`,color:tab===t?C.sage:C.muted,fontWeight:tab===t?700:400,cursor:"pointer",fontSize:13,marginBottom:-1,transition:"all .15s"}}>
                    {t==="about"?"Product Details":t==="reviews"?`Customer Reviews (${p.reviews.toLocaleString()})`:t==="shipping"?"Shipping & Returns":t}
                  </button>
                ))}
              </div>
              {tab==="about"&&<p style={{fontSize:13,color:C.mid,lineHeight:1.8}}>{p.name} — high-demand trending product. Quality tested, verified, and shipped within 24 hours from our US warehouse.</p>}
              {tab==="reviews"&&<div>{[["Sarah M.",5,"Exactly as described — fast shipping!","Got this for my desk and everyone loves it. Came in 4 days, well packaged."],["Mike T.",5,"Bought 3 more as gifts","Best price I found. Will definitely buy from LOOME again."],["Jordan K.",4,"Great quality for the price","Solid product, ships fast. Highly recommend."]].map(([n,r,t,b],i)=>(
                <div key={i} style={{borderBottom:`1px solid ${C.borderL}`,paddingBottom:12,marginBottom:12}}>
                  <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:4}}>
                    <div style={{width:28,height:28,borderRadius:"50%",background:C.pageBg,display:"flex",alignItems:"center",justifyContent:"center",border:`1px solid ${C.border}`}}>
                      <Icon name="user" size={14} color={C.muted} sw={1.8}/>
                    </div>
                    <span style={{fontSize:13,fontWeight:700}}>{n}</span>
                    <Stars rating={r} size={12}/>
                  </div>
                  <div style={{fontSize:13,fontWeight:700,color:C.dark,marginBottom:3}}>{t}</div>
                  <div style={{fontSize:12,color:C.mid}}>{b}</div>
                  <div style={{fontSize:11,color:C.green,fontWeight:600,marginTop:5,display:"flex",alignItems:"center",gap:4}}>
                    <Icon name="check" size={10} color={C.green} sw={2.5}/> Verified Purchase
                  </div>
                </div>
              ))}</div>}
              {tab==="shipping"&&<div style={{display:"flex",flexDirection:"column",gap:9}}>
                {[{n:"truck",t:"Standard (3–7 days)",d:"FREE on all LOOME orders",hi:true},{n:"bolt",t:"Expedited (2–3 days)",d:"$4.99"},{n:"rotate",t:"Free Returns",d:"30 days from delivery · Full refund"}].map(({n,t,d,hi})=>(
                  <div key={t} style={{display:"flex",gap:10,padding:"10px 12px",background:hi?"#F0FDF4":C.pageBg,borderRadius:6,border:`1px solid ${hi?"#BBF7D0":C.borderL}`}}>
                    <div style={{width:30,height:30,borderRadius:5,background:C.white,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${C.border}`}}><Icon name={n} size={14} color={C.sage} sw={1.8}/></div>
                    <div><div style={{fontSize:13,fontWeight:600,color:C.dark}}>{t}</div><div style={{fontSize:12,color:hi?C.green:C.muted}}>{d}</div></div>
                  </div>
                ))}
              </div>}
            </div>
          </div>

          {/* Buy box */}
          <div>
            <div style={{border:`1px solid ${C.border}`,borderRadius:8,padding:18,background:C.white,position:"sticky",top:82,boxShadow:"0 2px 12px rgba(0,0,0,.06)"}}>
              <div style={{display:"flex",alignItems:"baseline",gap:3,marginBottom:4}}>
                <span style={{fontSize:13,color:C.dark}}>$</span>
                <span style={{fontSize:28,fontWeight:800,color:C.dark,lineHeight:1}}>{p.price.toString().split(".")[0]}</span>
                <span style={{fontSize:13,color:C.dark,verticalAlign:"super"}}>{(p.price%1).toFixed(2).slice(1)}</span>
              </div>
              <div style={{fontSize:12,color:C.green,fontWeight:600,marginBottom:4}}>
                FREE delivery <strong>{p.shipDay}</strong>
              </div>
              <div style={{fontSize:12,color:C.dark,marginBottom:8}}>
                In Stock. <span style={{color:C.red,fontWeight:600}}>Only {p.stock} left.</span>
              </div>
              <div style={{height:1,background:C.borderL,marginBottom:12}}/>

              {/* Qty */}
              <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
                <span style={{fontSize:12,color:C.mid}}>Quantity:</span>
                <div style={{display:"flex",alignItems:"center",border:`1px solid ${C.border}`,borderRadius:4,overflow:"hidden"}}>
                  <button onClick={()=>setQty(q=>Math.max(1,q-1))} style={{width:26,height:28,border:"none",background:C.pageBg,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"}}><Icon name="minus" size={10} color={C.dark} sw={2}/></button>
                  <span style={{width:28,textAlign:"center",fontSize:13,fontWeight:700,color:C.dark}}>{qty}</span>
                  <button onClick={()=>setQty(q=>Math.min(5,q+1))} style={{width:26,height:28,border:"none",background:C.pageBg,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"}}><Icon name="plus" size={10} color={C.dark} sw={2}/></button>
                </div>
              </div>

              <button onClick={doAdd} style={{width:"100%",padding:"10px",background:added?"#3D6E47":C.addCart,border:"none",borderRadius:20,color:C.white,fontWeight:700,cursor:"pointer",fontSize:13,marginBottom:9,transition:"background .2s",display:"flex",alignItems:"center",justifyContent:"center",gap:6}}>
                {added?<><Icon name="check" size={13} color={C.white} sw={2.5}/>Added to Cart!</>:<><Icon name="cart" size={13} color={C.white} sw={2}/>Add to Cart</>}
              </button>
              <button onClick={doBuyNow} style={{width:"100%",padding:"10px",background:C.buyNow,border:"none",borderRadius:20,color:C.dark,fontWeight:800,cursor:"pointer",fontSize:13,marginBottom:16,boxShadow:"0 2px 8px rgba(255,164,28,.35)",display:"flex",alignItems:"center",justifyContent:"center",gap:6}}>
                <Icon name="bolt" size={12} color={C.dark} sw={2}/> Buy Now
              </button>

              <div style={{height:1,background:C.borderL,marginBottom:12}}/>
              {[{n:"shield",t:"Secure transaction"},{n:"rotate",t:"FREE Returns"},{n:"truck",t:"Ships from US"},{n:"msg",t:"24hr customer support"}].map(({n,t})=>(
                <div key={t} style={{display:"flex",gap:7,fontSize:12,color:C.mid,marginBottom:7,alignItems:"center"}}><Icon name={n} size={12} color={C.sage} sw={1.8}/>{t}</div>
              ))}
            </div>
          </div>
        </div>

        {/* Related */}
        <div style={{marginTop:32,background:C.white,borderRadius:8,padding:16,border:`1px solid ${C.border}`}}>
          <div style={{fontSize:18,fontWeight:700,color:C.dark,marginBottom:14}}>Customers who viewed this also viewed</div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:12}}>
            {related.map(rp=><ProductCard key={rp.id} p={rp} nav={nav} addToCart={addToCart} user={user} setShowLogin={setShowLogin} setBuyNowProduct={setBuyNowProduct}/>)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── CART ──────────────────────────────────────────────────────────────────────
function Cart({cart,setCart,nav,user,setShowLogin,setBuyNowProduct}){
  const sub=cart.reduce((s,i)=>s+i.price*i.qty,0);
  const saved=cart.reduce((s,i)=>s+(i.originalPrice-i.price)*i.qty,0);
  const upd=(id,q)=>setCart(c=>q<=0?c.filter(i=>i.id!==id):c.map(i=>i.id===id?{...i,qty:q}:i));
  return(
    <div style={{width:"100%",background:C.pageBg,minHeight:"80vh",padding:"16px",display:"flex",justifyContent:"center"}}>
      <div style={{width:"100%",maxWidth:1180}}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 300px",gap:18,alignItems:"start"}}>
          <div>
            <div style={{fontSize:24,fontWeight:400,color:C.dark,marginBottom:16,borderBottom:`1px solid ${C.border}`,paddingBottom:12}}>Shopping Cart</div>
            {cart.length===0?(
              <div style={{background:C.white,borderRadius:8,padding:48,textAlign:"center",border:`1px solid ${C.border}`}}>
                <Icon name="cart" size={44} color="#CCCCCC" sw={1}/>
                <div style={{fontSize:18,fontWeight:700,color:C.dark,marginTop:14,marginBottom:6}}>Your LOOME cart is empty</div>
                <div style={{fontSize:13,color:C.muted,marginBottom:18}}>Find something trending — you won't believe the prices.</div>
                <button onClick={()=>nav("home")} style={{padding:"10px 24px",background:C.sage,border:"none",borderRadius:6,color:C.white,fontWeight:700,cursor:"pointer",fontSize:13}}>Continue Shopping</button>
              </div>
            ):(
              <div style={{background:C.white,borderRadius:8,border:`1px solid ${C.border}`,overflow:"hidden"}}>
                {cart.map((item,idx)=>(
                  <div key={item.id} style={{display:"flex",gap:16,padding:16,borderBottom:idx<cart.length-1?`1px solid ${C.borderL}`:"none"}}>
                    <div onClick={()=>nav(`product:${item.id}`)} style={{width:100,height:100,background:C.imgBg,borderRadius:6,display:"flex",alignItems:"center",justifyContent:"center",cursor:"pointer",flexShrink:0,border:`1px solid ${C.borderL}`}}>
                      <Icon name={catIcon(item.category)} size={44} color="#BBBBBB" sw={1}/>
                    </div>
                    <div style={{flex:1}}>
                      <div onClick={()=>nav(`product:${item.id}`)} style={{fontSize:14,fontWeight:400,color:"#007185",cursor:"pointer",marginBottom:4,lineHeight:1.4}}>{item.name}</div>
                      <div style={{fontSize:12,color:C.green,fontWeight:600,marginBottom:8}}>In Stock · FREE delivery {item.shipDay}</div>
                      <div style={{display:"flex",gap:10,alignItems:"center"}}>
                        <div style={{display:"flex",alignItems:"center",border:`1px solid ${C.border}`,borderRadius:4,overflow:"hidden"}}>
                          <button onClick={()=>upd(item.id,item.qty-1)} style={{width:26,height:26,border:"none",background:C.pageBg,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"}}><Icon name="minus" size={10} color={C.dark} sw={2}/></button>
                          <span style={{width:28,textAlign:"center",fontSize:13,fontWeight:700}}>{item.qty}</span>
                          <button onClick={()=>upd(item.id,item.qty+1)} style={{width:26,height:26,border:"none",background:C.pageBg,cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center"}}><Icon name="plus" size={10} color={C.dark} sw={2}/></button>
                        </div>
                        <span style={{color:C.border}}>|</span>
                        <button onClick={()=>upd(item.id,0)} style={{background:"none",border:"none",color:"#007185",fontSize:12,cursor:"pointer"}}>Delete</button>
                        <span style={{color:C.border}}>|</span>
                        <button onClick={()=>nav(`product:${item.id}`)} style={{background:"none",border:"none",color:"#007185",fontSize:12,cursor:"pointer"}}>View Item</button>
                      </div>
                    </div>
                    <div style={{textAlign:"right",flexShrink:0}}>
                      <div style={{fontSize:18,fontWeight:800,color:C.dark}}>${(item.price*item.qty).toFixed(2)}</div>
                      {item.qty>1&&<div style={{fontSize:10,color:C.muted}}>${item.price} each</div>}
                    </div>
                  </div>
                ))}
                <div style={{padding:"12px 16px",textAlign:"right",fontSize:16,color:C.dark,borderTop:`1px solid ${C.borderL}`}}>
                  Subtotal ({cart.reduce((s,i)=>s+i.qty,0)} items): <strong>${sub.toFixed(2)}</strong>
                  {saved>0&&<div style={{fontSize:12,color:C.limitedDeal}}>Your savings: ${saved.toFixed(2)}</div>}
                </div>
              </div>
            )}
          </div>

          {/* Summary */}
          {cart.length>0&&<div style={{background:C.white,borderRadius:8,padding:16,border:`1px solid ${C.border}`,position:"sticky",top:82}}>
            <div style={{fontSize:12,color:C.green,fontWeight:600,marginBottom:12}}>Your order qualifies for FREE Shipping.</div>
            <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:14}}>
              Subtotal ({cart.reduce((s,i)=>s+i.qty,0)} items): <span style={{color:C.dark}}>${sub.toFixed(2)}</span>
              {saved>0&&<div style={{fontSize:12,color:C.limitedDeal,fontWeight:600}}>You save: ${saved.toFixed(2)}</div>}
            </div>
            <button onClick={()=>nav("checkout")} style={{width:"100%",padding:"11px",background:C.buyNow,border:"none",borderRadius:20,fontWeight:800,cursor:"pointer",fontSize:14,color:C.dark,marginBottom:8,boxShadow:"0 2px 8px rgba(255,164,28,.35)"}}>
              Proceed to Checkout
            </button>
            <button onClick={()=>nav("home")} style={{width:"100%",padding:"9px",background:C.white,border:`1px solid ${C.border}`,borderRadius:20,cursor:"pointer",fontSize:12,color:C.dark}}>
              Continue Shopping
            </button>
          </div>}
        </div>
      </div>
    </div>
  );
}

// ── CHECKOUT ──────────────────────────────────────────────────────────────────
function Checkout({cart,nav,setCart,user,setUser}){
  const [step,setStep]=useState(1);
  const [f,setF]=useState({name:user?.addresses?.[0]?.name||"",street:user?.addresses?.[0]?.street||"",city:user?.addresses?.[0]?.city||"",zip:user?.addresses?.[0]?.zip||"",card:"",exp:"",cvv:""});
  const [selCard,setSelCard]=useState(user?.cards?.[0]||null);
  const [useNew,setUseNew]=useState(!user?.cards?.length);
  const [saveCard,setSaveCard]=useState(true);
  const sub=cart.reduce((s,i)=>s+i.price*i.qty,0);
  const upd=(k,v)=>setF(x=>({...x,[k]:v}));

  const place=()=>{
    if(saveCard&&f.card&&user){
      const masked="•••• •••• •••• "+f.card.replace(/\s/g,"").slice(-4);
      setUser(u=>{const updated={...u,cards:[...(u.cards||[]),{masked,exp:f.exp,id:Date.now()}]};localStorage.setItem("loome_user",JSON.stringify(updated));return updated;});
    }
    if(user&&f.street){
      const addr={name:f.name,street:f.street,city:f.city,zip:f.zip};
      setUser(u=>{const updated={...u,addresses:[addr,...(u.addresses||[]).filter(a=>a.street!==f.street)]};localStorage.setItem("loome_user",JSON.stringify(updated));return updated;});
    }
    setStep(3);
  };

  const Field=({label,k,ph,half,type="text"})=>(
    <div style={{flex:half?"1":"unset",marginBottom:12}}>
      <label style={{fontSize:11,color:C.mid,display:"block",marginBottom:4,fontWeight:500}}>{label}</label>
      <input value={f[k]} onChange={e=>upd(k,e.target.value)} placeholder={ph} type={type}
        style={{width:"100%",padding:"9px 11px",border:`1px solid ${C.border}`,borderRadius:4,fontSize:13,outline:"none",transition:"border-color .15s"}}
        onFocus={e=>e.target.style.borderColor=C.sage} onBlur={e=>e.target.style.borderColor=C.border}/>
    </div>
  );

  if(step===3) return(
    <div style={{background:C.pageBg,minHeight:"80vh",display:"flex",alignItems:"center",justifyContent:"center",padding:20}}>
      <div style={{background:C.white,borderRadius:10,padding:42,textAlign:"center",maxWidth:460,boxShadow:"0 6px 28px rgba(0,0,0,.1)",border:`1px solid ${C.border}`}}>
        <div style={{width:56,height:56,borderRadius:"50%",background:C.sageL,display:"flex",alignItems:"center",justifyContent:"center",margin:"0 auto 14px"}}>
          <Icon name="check" size={28} color={C.sage} sw={2.5}/>
        </div>
        <div style={{fontSize:24,fontWeight:700,color:C.dark,marginBottom:6}}>Order Confirmed!</div>
        <div style={{fontSize:13,color:C.mid,marginBottom:20}}>Your order ships within 24 hours. You'll receive email updates.</div>
        <div style={{background:C.pageBg,borderRadius:8,padding:14,marginBottom:20,textAlign:"left"}}>
          {cart.map(i=>(<div key={i.id} style={{display:"flex",justifyContent:"space-between",fontSize:12,marginBottom:5}}>
            <span>{i.name} ×{i.qty}</span><span style={{fontWeight:700}}>${(i.price*i.qty).toFixed(2)}</span>
          </div>))}
          <div style={{height:1,background:C.borderL,margin:"8px 0"}}/>
          <div style={{display:"flex",justifyContent:"space-between",fontWeight:800,fontSize:14}}><span>Total</span><span>${sub.toFixed(2)}</span></div>
        </div>
        <button onClick={()=>{setCart([]);nav("home");}} style={{padding:"12px 28px",background:C.sage,border:"none",borderRadius:6,color:C.white,fontWeight:700,cursor:"pointer",fontSize:13}}>
          Continue Shopping
        </button>
      </div>
    </div>
  );

  return(
    <div style={{width:"100%",background:C.pageBg,minHeight:"80vh",padding:"16px",display:"flex",justifyContent:"center"}}>
      <div style={{width:"100%",maxWidth:900,display:"grid",gridTemplateColumns:"1fr 280px",gap:18}}>
        <div>
          <div style={{display:"flex",gap:8,marginBottom:18,alignItems:"center"}}>
            {["Shipping","Payment","Review"].slice(0,2).map((s,i)=>(
              <div key={s} style={{display:"flex",alignItems:"center",gap:6}}>
                <div style={{width:24,height:24,borderRadius:"50%",background:step>i+1?C.green:step===i+1?C.sage:C.border,color:C.white,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:700}}>
                  {step>i+1?<Icon name="check" size={11} color={C.white} sw={2.5}/>:i+1}
                </div>
                <span style={{fontSize:13,color:step===i+1?C.dark:C.muted,fontWeight:step===i+1?700:400}}>{s}</span>
                {i<1&&<Icon name="chevR" size={13} color={C.light} sw={2}/>}
              </div>
            ))}
          </div>

          <div style={{background:C.white,borderRadius:8,padding:22,border:`1px solid ${C.border}`}}>
            {step===1&&<>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:18,display:"flex",alignItems:"center",gap:8}}>
                <Icon name="truck" size={17} color={C.sage} sw={1.8}/> Shipping Address
              </div>
              {user?.addresses?.length>0&&<div style={{marginBottom:14}}>
                {user.addresses.map((a,i)=>(
                  <div key={i} onClick={()=>setF(x=>({...x,...a}))} style={{padding:"8px 12px",border:`1px solid ${f.street===a.street?C.sage:C.border}`,borderRadius:5,marginBottom:6,cursor:"pointer",fontSize:12,background:f.street===a.street?C.sageL:C.white,display:"flex",alignItems:"center",gap:8}}>
                    <Icon name="home2" size={13} color={f.street===a.street?C.sage:C.muted} sw={1.8}/>
                    {a.name} — {a.street}, {a.city} {a.zip}
                  </div>
                ))}
                <div style={{fontSize:12,color:C.muted,marginBottom:12}}>Or enter a new address:</div>
              </div>}
              <Field label="Full Name" k="name" ph="Your full name"/>
              <Field label="Street Address" k="street" ph="123 Main Street"/>
              <div style={{display:"flex",gap:12}}><Field label="City" k="city" ph="City" half/><Field label="ZIP Code" k="zip" ph="90210" half/></div>
              <button onClick={()=>setStep(2)} style={{padding:"11px 24px",background:C.sage,border:"none",borderRadius:6,color:C.white,fontWeight:700,cursor:"pointer",fontSize:13,display:"flex",alignItems:"center",gap:6}}>
                Continue <Icon name="arrowR" size={13} color={C.white} sw={2}/>
              </button>
            </>}
            {step===2&&<>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:18,display:"flex",alignItems:"center",gap:8}}>
                <Icon name="lock" size={17} color={C.sage} sw={1.8}/> Payment Method
              </div>
              {user?.cards?.length>0&&!useNew&&(
                <div style={{marginBottom:14}}>
                  {user.cards.map((card,i)=>(
                    <div key={i} onClick={()=>setSelCard(card)} style={{padding:"10px 12px",border:`1px solid ${selCard?.id===card.id?C.sage:C.border}`,borderRadius:5,marginBottom:6,cursor:"pointer",display:"flex",alignItems:"center",gap:10,background:selCard?.id===card.id?C.sageL:C.white}}>
                      <Icon name="card" size={16} color={selCard?.id===card.id?C.sage:C.mid} sw={1.5}/>
                      <div style={{flex:1}}>
                        <div style={{fontSize:13,fontWeight:600}}>{card.masked}</div>
                        <div style={{fontSize:11,color:C.muted}}>Expires {card.exp}</div>
                      </div>
                      {selCard?.id===card.id&&<Icon name="check" size={14} color={C.sage} sw={2.5}/>}
                    </div>
                  ))}
                  <button onClick={()=>setUseNew(true)} style={{fontSize:12,color:C.sage,background:"none",border:"none",cursor:"pointer",padding:0,marginBottom:12}}>+ Use a new card</button>
                </div>
              )}
              {(useNew||!user?.cards?.length)&&(
                <div>
                  <Field label="Card Number" k="card" ph="1234 5678 9012 3456"/>
                  <div style={{display:"flex",gap:12}}><Field label="Expiry (MM/YY)" k="exp" ph="12/27" half/><Field label="CVV" k="cvv" ph="•••" half type="password"/></div>
                  {user&&<label style={{display:"flex",alignItems:"center",gap:7,fontSize:12,color:C.mid,cursor:"pointer",marginBottom:14}}>
                    <input type="checkbox" checked={saveCard} onChange={e=>setSaveCard(e.target.checked)} style={{accentColor:C.sage}}/>
                    Save card to my LOOME account
                  </label>}
                </div>
              )}
              <div style={{display:"flex",gap:9}}>
                <button onClick={()=>setStep(1)} style={{padding:"10px 18px",background:C.white,border:`1px solid ${C.border}`,borderRadius:5,cursor:"pointer",fontSize:12,color:C.dark}}>← Back</button>
                <button onClick={place} style={{padding:"11px 24px",background:C.buyNow,border:"none",borderRadius:6,fontWeight:800,cursor:"pointer",fontSize:13,color:C.dark,boxShadow:"0 2px 8px rgba(255,164,28,.35)"}}>
                  Place Order — ${sub.toFixed(2)}
                </button>
              </div>
            </>}
          </div>
        </div>

        {/* Summary */}
        <div style={{background:C.white,borderRadius:8,padding:16,border:`1px solid ${C.border}`,height:"fit-content",position:"sticky",top:82}}>
          <div style={{fontSize:14,fontWeight:700,color:C.dark,marginBottom:12}}>Order Summary</div>
          {cart.map(i=>(
            <div key={i.id} style={{display:"flex",gap:8,marginBottom:9,alignItems:"center"}}>
              <div style={{width:44,height:44,background:C.imgBg,borderRadius:5,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${C.borderL}`}}>
                <Icon name={catIcon(i.category)} size={20} color="#BBBBBB" sw={1}/>
              </div>
              <div style={{flex:1,fontSize:11,color:C.dark,lineHeight:1.3}}>{i.name}<br/><span style={{color:C.muted}}>Qty: {i.qty}</span></div>
              <div style={{fontSize:12,fontWeight:700}}>${(i.price*i.qty).toFixed(2)}</div>
            </div>
          ))}
          <div style={{height:1,background:C.borderL,margin:"10px 0"}}/>
          {[["Subtotal",`$${sub.toFixed(2)}`],["Shipping","FREE"],["Tax","Included"]].map(([l,v])=>(
            <div key={l} style={{display:"flex",justifyContent:"space-between",fontSize:12,marginBottom:6}}>
              <span style={{color:C.muted}}>{l}</span><span style={{color:v==="FREE"?C.green:C.dark,fontWeight:v==="FREE"?600:400}}>{v}</span>
            </div>
          ))}
          <div style={{height:1,background:C.borderL,margin:"10px 0"}}/>
          <div style={{display:"flex",justifyContent:"space-between",fontSize:15,fontWeight:800,color:C.dark}}><span>Order Total</span><span>${sub.toFixed(2)}</span></div>
        </div>
      </div>
    </div>
  );
}

// ── ACCOUNT ───────────────────────────────────────────────────────────────────
function Account({nav,user,setUser,setShowLogin}){
  const [tab,setTab]=useState("orders");
  if(!user) return(
    <div style={{background:C.pageBg,minHeight:"80vh",display:"flex",alignItems:"center",justifyContent:"center"}}>
      <div style={{background:C.white,borderRadius:10,padding:42,textAlign:"center",maxWidth:380,border:`1px solid ${C.border}`}}>
        <Logo light={false}/>
        <div style={{fontSize:18,fontWeight:700,color:C.dark,marginTop:16,marginBottom:6}}>Sign in to your account</div>
        <div style={{fontSize:13,color:C.muted,marginBottom:20}}>Access your orders, saved addresses, and payment methods.</div>
        <button onClick={()=>setShowLogin(true)} style={{width:"100%",padding:"11px",background:C.sage,border:"none",borderRadius:6,color:C.white,fontWeight:700,cursor:"pointer",fontSize:14}}>Sign In / Create Account</button>
      </div>
    </div>
  );

  const removeCard=(id)=>setUser(u=>{const updated={...u,cards:u.cards.filter(c=>c.id!==id)};localStorage.setItem("loome_user",JSON.stringify(updated));return updated;});
  const removeAddr=(street)=>setUser(u=>{const updated={...u,addresses:u.addresses.filter(a=>a.street!==street)};localStorage.setItem("loome_user",JSON.stringify(updated));return updated;});

  return(
    <div style={{width:"100%",background:C.pageBg,minHeight:"80vh",padding:"16px",display:"flex",justifyContent:"center"}}>
      <div style={{width:"100%",maxWidth:1040}}>
        <div style={{fontSize:22,fontWeight:700,color:C.dark,marginBottom:16}}>Hello, {user.name}</div>
        <div style={{display:"grid",gridTemplateColumns:"200px 1fr",gap:16}}>
          <div style={{background:C.white,borderRadius:8,padding:12,border:`1px solid ${C.border}`,height:"fit-content"}}>
            {[{id:"orders",n:"box",l:"My Orders"},{id:"payment",n:"card",l:"Payment Methods"},{id:"addresses",n:"home2",l:"Addresses"},{id:"settings",n:"user",l:"Account Settings"}].map(({id,n,l})=>(
              <button key={id} onClick={()=>setTab(id)} style={{width:"100%",display:"flex",alignItems:"center",gap:9,padding:"9px 10px",borderRadius:5,cursor:"pointer",fontSize:13,fontWeight:tab===id?700:400,color:tab===id?C.sage:C.dark,background:tab===id?C.sageL:"transparent",border:"none",marginBottom:2,textAlign:"left"}}>
                <Icon name={n} size={14} color={tab===id?C.sage:C.muted} sw={1.8}/>{l}
              </button>
            ))}
          </div>
          <div style={{background:C.white,borderRadius:8,padding:20,border:`1px solid ${C.border}`}}>
            {tab==="orders"&&<div>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:14}}>Your Orders</div>
              {PRODUCTS.slice(0,5).map((p,i)=>(
                <div key={p.id} style={{display:"flex",gap:12,padding:"12px 0",borderBottom:`1px solid ${C.borderL}`,alignItems:"center"}}>
                  <div style={{width:52,height:52,background:C.imgBg,borderRadius:6,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,border:`1px solid ${C.borderL}`}}>
                    <Icon name={catIcon(p.category)} size={24} color="#BBBBBB" sw={1}/>
                  </div>
                  <div style={{flex:1}}>
                    <div style={{fontSize:13,fontWeight:400,color:"#007185",cursor:"pointer"}} onClick={()=>nav(`product:${p.id}`)}>{p.name}</div>
                    <div style={{fontSize:11,color:C.muted,marginTop:2}}>Ordered {["2 days ago","1 week ago","2 weeks ago","3 weeks ago","1 month ago"][i]}</div>
                  </div>
                  <div style={{textAlign:"right"}}>
                    <div style={{fontSize:14,fontWeight:700,color:C.dark}}>${p.price}</div>
                    <div style={{fontSize:11,color:C.green}}>Delivered</div>
                  </div>
                  <button onClick={()=>{addToCartDummy(p);}} style={{padding:"6px 14px",background:C.pageBg,border:`1px solid ${C.border}`,borderRadius:4,fontSize:12,cursor:"pointer",color:C.dark}}>Buy again</button>
                </div>
              ))}
            </div>}
            {tab==="payment"&&<div>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:14}}>Saved Payment Methods</div>
              {(!user.cards||user.cards.length===0)&&<div style={{fontSize:13,color:C.muted,marginBottom:12}}>No saved cards yet. Add one during checkout.</div>}
              {user.cards?.map((card)=>(
                <div key={card.id} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 14px",border:`1px solid ${C.border}`,borderRadius:7,marginBottom:9}}>
                  <Icon name="card" size={22} color={C.sage} sw={1.5}/>
                  <div style={{flex:1}}>
                    <div style={{fontSize:13,fontWeight:700,color:C.dark}}>{card.masked}</div>
                    <div style={{fontSize:11,color:C.muted}}>Expires {card.exp}</div>
                  </div>
                  <button onClick={()=>removeCard(card.id)} style={{padding:"5px 12px",background:"none",border:`1px solid ${C.border}`,borderRadius:4,fontSize:11,cursor:"pointer",color:C.red}}>Remove</button>
                </div>
              ))}
            </div>}
            {tab==="addresses"&&<div>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:14}}>Saved Addresses</div>
              {(!user.addresses||user.addresses.length===0)&&<div style={{fontSize:13,color:C.muted}}>No saved addresses yet. They'll be saved automatically when you checkout.</div>}
              {user.addresses?.map((a,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:12,padding:"12px 14px",border:`1px solid ${C.border}`,borderRadius:7,marginBottom:9}}>
                  <Icon name="home2" size={20} color={C.sage} sw={1.6}/>
                  <div style={{flex:1}}>
                    <div style={{fontSize:13,fontWeight:700,color:C.dark}}>{a.name}</div>
                    <div style={{fontSize:12,color:C.muted}}>{a.street}, {a.city} {a.zip}</div>
                  </div>
                  <button onClick={()=>removeAddr(a.street)} style={{padding:"5px 12px",background:"none",border:`1px solid ${C.border}`,borderRadius:4,fontSize:11,cursor:"pointer",color:C.red}}>Remove</button>
                </div>
              ))}
            </div>}
            {tab==="settings"&&<div>
              <div style={{fontSize:16,fontWeight:700,color:C.dark,marginBottom:14}}>Account Settings</div>
              {[["Full Name",user.name],["Email",user.email],["Member Since","April 2025"]].map(([l,v])=>(
                <div key={l} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"12px 0",borderBottom:`1px solid ${C.borderL}`}}>
                  <span style={{fontSize:13,color:C.muted}}>{l}</span>
                  <div style={{display:"flex",gap:12,alignItems:"center"}}>
                    <span style={{fontSize:13,fontWeight:500,color:C.dark}}>{v}</span>
                    <button style={{padding:"4px 12px",background:"none",border:`1px solid ${C.border}`,borderRadius:4,fontSize:11,cursor:"pointer",color:"#007185"}}>Edit</button>
                  </div>
                </div>
              ))}
            </div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function addToCartDummy(){}

// ── FOOTER ────────────────────────────────────────────────────────────────────
function Footer({nav}){
  return(
    <footer style={{background:C.iron,padding:"32px 16px 16px"}}>
      <div style={{maxWidth:1380,margin:"0 auto"}}>
        <div style={{display:"grid",gridTemplateColumns:"2fr 1fr 1fr 1fr 1.3fr",gap:24,marginBottom:24}}>
          <div>
            <div style={{marginBottom:10,cursor:"pointer"}} onClick={()=>nav("home")}><Logo/></div>
            <div style={{fontSize:12,color:"rgba(255,255,255,.5)",lineHeight:1.8,marginBottom:14}}>Find it before everyone else. Trending products at unbeatable prices, updated daily by AI.</div>
          </div>
          {[["GET TO KNOW US",["About LOOME","Careers","Press","Investor Relations"]],["MAKE MONEY WITH US",["Sell on LOOME","Affiliate Program","Advertise"]],["LET US HELP YOU",["Your Account","Track Orders","Returns","Customer Service","FAQ"]]].map(([h,links])=>(
            <div key={h}>
              <div style={{fontSize:10,fontWeight:700,letterSpacing:".12em",color:C.wheat,marginBottom:10}}>{h}</div>
              {links.map(l=><div key={l} onClick={()=>nav("home")} style={{fontSize:12,color:"rgba(255,255,255,.45)",marginBottom:7,cursor:"pointer"}}
                onMouseEnter={e=>e.target.style.color=C.white} onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.45)"}>{l}</div>)}
            </div>
          ))}
          <div>
            <div style={{fontSize:10,fontWeight:700,letterSpacing:".12em",color:C.wheat,marginBottom:10}}>DEAL ALERTS</div>
            <div style={{fontSize:12,color:"rgba(255,255,255,.45)",marginBottom:10,lineHeight:1.7}}>First to know = first to save.</div>
            <input placeholder="your@email.com" style={{width:"100%",padding:"8px 10px",background:"rgba(255,255,255,.08)",border:"1px solid rgba(255,255,255,.15)",borderRadius:4,color:C.white,fontSize:12,marginBottom:7,outline:"none"}}/>
            <button style={{width:"100%",padding:"8px",background:C.sage,border:"none",borderRadius:4,color:C.white,fontSize:12,fontWeight:700,cursor:"pointer"}}>Subscribe</button>
          </div>
        </div>
        <div style={{height:1,background:"rgba(255,255,255,.08)",marginBottom:12}}/>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:11,color:"rgba(255,255,255,.28)",flexWrap:"wrap",gap:6}}>
          <span>© 2025 LOOME Inc.</span>
          <div style={{display:"flex",gap:12}}>
            {["Privacy","Terms","Cookies"].map(l=><span key={l} style={{cursor:"pointer"}}
              onMouseEnter={e=>e.target.style.color="rgba(255,255,255,.6)"} onMouseLeave={e=>e.target.style.color="rgba(255,255,255,.28)"}>{l}</span>)}
          </div>
        </div>
      </div>
    </footer>
  );
}

function Toast({msg}){
  return msg?<div style={{position:"fixed",bottom:20,left:"50%",transform:"translateX(-50%)",background:C.iron,color:C.white,padding:"9px 18px",borderRadius:20,fontSize:12,fontWeight:600,zIndex:9999,boxShadow:"0 4px 18px rgba(0,0,0,.2)",display:"flex",alignItems:"center",gap:7,whiteSpace:"nowrap"}}>
    <Icon name="check" size={12} color={C.sage} sw={2.5}/> {msg}
  </div>:null;
}

// ── APP ───────────────────────────────────────────────────────────────────────
export default function LooMeStore(){
  const [page,setPage]=useState("home");
  const [cart,setCart]=useState([]);
  const [cat,setCat]=useState("All");
  const [search,setSearch]=useState("");
  const [toast,setToast]=useState("");
  const [user,setUser]=useState(()=>JSON.parse(localStorage.getItem("loome_user")||"null"));
  const [showLogin,setShowLogin]=useState(false);
  const [buyNowProduct,setBuyNowProduct]=useState(null);

  const nav=(p)=>setPage(p);
  const addToCart=(product)=>{
    setCart(c=>{const ex=c.find(i=>i.id===product.id);return ex?c.map(i=>i.id===product.id?{...i,qty:i.qty+1}:i):[...c,{...product,qty:1}];});
    setToast(`${product.name.split(" ").slice(0,3).join(" ")} added to cart`);
    setTimeout(()=>setToast(""),2200);
  };

  const pid=page.startsWith("product:")?+page.split(":")[1]:null;

  return(
    <div style={{minHeight:"100vh",background:C.pageBg,fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        @keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        body,button,input,select{font-family:'DM Sans',sans-serif;}
        ::-webkit-scrollbar{width:5px;height:5px;}
        ::-webkit-scrollbar-thumb{background:#CCCCCC;border-radius:3px;}
      `}</style>

      <Header cart={cart} nav={nav} setSearch={s=>{setSearch(s);nav("home");}} setCat={c=>{setCat(c);}} user={user} setShowLogin={setShowLogin} setUser={setUser}/>

      {page==="home"&&<>
        <TrustBanner/>
        <Home nav={nav} addToCart={addToCart} cat={cat} search={search} user={user} setShowLogin={setShowLogin} setBuyNowProduct={setBuyNowProduct}/>
      </>}
      {pid&&<ProductDetail id={pid} nav={nav} addToCart={addToCart} user={user} setShowLogin={setShowLogin} setBuyNowProduct={setBuyNowProduct}/>}
      {page==="cart"&&<Cart cart={cart} setCart={setCart} nav={nav} user={user} setShowLogin={setShowLogin} setBuyNowProduct={setBuyNowProduct}/>}
      {page==="checkout"&&<Checkout cart={cart} nav={nav} setCart={setCart} user={user} setUser={setUser}/>}
      {page==="account"&&<Account nav={nav} user={user} setUser={setUser} setShowLogin={setShowLogin}/>}
      {page==="dads"&&<OakwoodDads/>}

      <Footer nav={nav}/>
      <Toast msg={toast}/>

      {showLogin&&<LoginModal onClose={()=>setShowLogin(false)} setUser={setUser} setToast={(m)=>{setToast(m);setTimeout(()=>setToast(""),3000);}}/>}
      {buyNowProduct&&<BuyNowModal product={buyNowProduct} user={user} setUser={setUser} onClose={()=>setBuyNowProduct(null)} setPage={setPage}/>}
    </div>
  );
}
