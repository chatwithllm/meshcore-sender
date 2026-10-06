const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const vendor = path.resolve(__dirname,'../custom_components/meshcore_sender/www/vendor');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(vendor,'point-in-polygon.js'),'utf8'),context);
const features = JSON.parse(fs.readFileSync(path.join(vendor,'us-states.json'),'utf8')).features;
const classify = (lat,lon) => features.find(f=>context.MeshCoreGeo.booleanPointInPolygon([lon,lat],f))?.properties.code;
for (const [lat,lon,code] of [
  [36.38932,-86.262,'TN'],[39.70739,-85.99339,'IN'],[39.9612,-82.9988,'OH'],
  [38.2527,-85.7585,'KY'],[38.3498,-81.6326,'WV'],[35.7796,-78.6382,'NC'],
  [37.5407,-77.436,'VA'],[41.8781,-87.6298,'IL'],[28.5383,-81.3792,'FL'],
  [40.7128,-74.006,'NY'],[34.0522,-118.2437,'CA'],[61.2181,-149.9003,'AK'],
  [21.3069,-157.8583,'HI'],[38.9072,-77.0369,'DC'],[18.4655,-66.1057,'PR'],
  [43.6532,-79.3832,undefined],[-33.8688,151.2093,undefined]
]) assert.equal(classify(lat,lon),code,`State at ${lat},${lon}`);
const polygon={type:'Polygon',coordinates:[[[0,0],[10,0],[10,10],[0,10],[0,0]],[[2,2],[2,4],[4,4],[4,2],[2,2]]]};
assert.equal(context.MeshCoreGeo.booleanPointInPolygon([3,3],polygon),false,'Respect polygon holes');
assert.equal(context.MeshCoreGeo.booleanPointInPolygon([1,1],polygon),true);
console.log('State geography checks passed, including Alaska, Hawaii, DC, Puerto Rico and unknown locations.');
