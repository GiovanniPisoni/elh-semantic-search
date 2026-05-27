"""
Canvas-based loading and completion animations.

The loading animation shows a small character running left-to-right past a
row of houses, painting each one as they pass. The completion animation
freezes the runner at the last house with a celebration pose.
"""

from __future__ import annotations

LOADING_HTML = """<!DOCTYPE html>
<html>
<body style="margin:0;padding:1px 0 0;background:#fff;font-family:system-ui;">
<canvas id="cv" height="24" style="width:100%;height:24px;display:block;"></canvas>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  var N=14,rx=-12,t=0;
  function resize(){cv.width=cv.offsetWidth||400;}resize();
  function house(cx,filled){
    var H=cv.height,gnd=H-2,w=12,h=14,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle=filled?'#1D4ED8':'#CBD5E1';ctx.lineWidth=1;ctx.lineJoin='round';
    ctx.fillStyle=filled?'rgba(29,78,216,0.09)':'rgba(0,0,0,0)';
    ctx.beginPath();ctx.moveTo(bx-1,by+h*0.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+1,by+h*0.42);ctx.lineTo(bx+w+1,by+h);ctx.lineTo(bx-1,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=3,dh=5,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle=filled?'#1D4ED8':'#CBD5E1';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*0.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
  }
  function runner(x){
    var H=cv.height,gnd=H-2,ph=t*0.3,C='#1D4ED8',CD='#1E40AF',gy=gnd;
    ctx.strokeStyle=C;ctx.lineWidth=1.2;ctx.lineCap='round';
    var l1=Math.sin(ph)*3,l2=Math.sin(ph+Math.PI)*3;
    var lly=Math.abs(Math.cos(ph))*3,lry=Math.abs(Math.cos(ph+Math.PI))*3;
    ctx.beginPath();ctx.moveTo(x,gy-5);ctx.lineTo(x+l1*.5,gy-2.5);ctx.lineTo(x+l1,gy-lly);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x,gy-5);ctx.lineTo(x+l2*.5,gy-2.5);ctx.lineTo(x+l2,gy-lry);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.roundRect(x-1.5,gy-11,3,6,1);ctx.fill();
    ctx.strokeStyle=CD;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x-1,gy-10);ctx.lineTo(x-1+Math.sin(ph+Math.PI)*3,gy-7);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1,gy-10);ctx.lineTo(x+1+Math.sin(ph)*3,gy-7);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.arc(x,gy-13.5,2.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=CD;ctx.beginPath();ctx.arc(x,gy-15,1.8,Math.PI,0);ctx.fill();
  }
  function loop(){
    var W=cv.offsetWidth||400;if(cv.width!==W)cv.width=W;
    ctx.clearRect(0,0,W,cv.height);
    var sw=W/N,np=Math.max(-1,Math.floor((rx-sw*.1)/sw));
    for(var i=0;i<N;i++)house(sw*i+sw/2,i<=np);
    if(rx>-15&&rx<W+15)runner(rx);
    rx+=3;t++;if(rx>W+20)rx=-15;
    requestAnimationFrame(loop);
  }
  loop();
})();
</script>
</body>
</html>"""


DONE_HTML = """<!DOCTYPE html>
<html>
<body style="margin:0;padding:1px 0 0;background:#fff;font-family:system-ui;">
<canvas id="cv" height="24" style="width:100%;height:24px;display:block;"></canvas>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  cv.width=cv.offsetWidth||400;
  var N=14,H=cv.height,W=cv.width,sw=W/N,t=0;
  function house(cx){
    var gnd=H-2,w=12,h=14,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle='#16A34A';ctx.lineWidth=1;ctx.lineJoin='round';
    ctx.fillStyle='rgba(22,163,74,0.09)';
    ctx.beginPath();ctx.moveTo(bx-1,by+h*.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+1,by+h*.42);ctx.lineTo(bx+w+1,by+h);ctx.lineTo(bx-1,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=3,dh=5,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle='#16A34A';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#16A34A';ctx.lineWidth=.8;ctx.lineCap='round';
    ctx.beginPath();ctx.moveTo(cx-2.5,by+h*.52);ctx.lineTo(cx-.5,by+h*.7);ctx.lineTo(cx+3,by+h*.35);ctx.stroke();
  }
  function celebrant(){
    var gnd=H-2,x=sw*(N-0.5),bounce=Math.abs(Math.sin(t*.15))*5,y=gnd-bounce;
    var C='#16A34A',CD='#166534';
    ctx.fillStyle=C;ctx.beginPath();ctx.arc(x,y-13.5,2.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=CD;ctx.beginPath();ctx.arc(x,y-15,1.8,Math.PI,0);ctx.fill();
    ctx.fillStyle=C;ctx.beginPath();ctx.roundRect(x-1.5,y-11,3,6,1);ctx.fill();
    ctx.strokeStyle=C;ctx.lineWidth=1.2;ctx.lineCap='round';
    ctx.beginPath();ctx.moveTo(x-1.5,y-9);ctx.lineTo(x-5,y-14);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1.5,y-9);ctx.lineTo(x+5,y-14);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x-1,y-5);ctx.lineTo(x-1.5,y);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1,y-5);ctx.lineTo(x+1.5,y);ctx.stroke();
    var op=(Math.sin(t*.2)+1)/2*.8+.2;
    ctx.fillStyle='rgba(22,163,74,'+op.toFixed(2)+')';
    [[-6,-4],[6,-5],[0,-10],[-4,-8],[5,-3]].forEach(function(s){
      ctx.beginPath();ctx.arc(x+s[0],y+s[1],1.2,0,Math.PI*2);ctx.fill();
    });
  }
  function draw(){
    var W2=cv.offsetWidth||400;if(cv.width!==W2){cv.width=W2;W=W2;}
    ctx.clearRect(0,0,W,H);
    for(var i=0;i<N;i++)house(sw*i+sw/2);
    celebrant(); t++;
    requestAnimationFrame(draw);
  }
  draw();
})();
</script>
</body>
</html>"""
