// Decode Nuxt's literal state format without executing downloaded JavaScript.
const fs=require('node:fs');
const {parseExpression}=require('../frontend/node_modules/@babel/parser');
const forbidden=new Set(['__proto__','prototype','constructor']);
let steps=0;
function value(node,scope){
  if(++steps>500000)throw Error('State too complex');
  switch(node.type){
    case 'StringLiteral':case 'NumericLiteral':case 'BooleanLiteral':return node.value;
    case 'NullLiteral':return null;
    case 'Identifier':if(Object.hasOwn(scope,node.name))return scope[node.name];throw Error('Unknown state identifier');
    case 'UnaryExpression':if(node.operator==='-'||node.operator==='!')return node.operator==='-'?-value(node.argument,scope):!value(node.argument,scope);break;
    case 'ArrayExpression':return node.elements.map(n=>n?value(n,scope):null);
    case 'ObjectExpression':{
      const obj=Object.create(null);
      for(const prop of node.properties){if(prop.type!=='ObjectProperty'||prop.computed)throw Error('Unsupported state property');const key=prop.key.name??prop.key.value;if(forbidden.has(key))throw Error('Unsafe state key');obj[key]=value(prop.value,scope)}
      return obj;
    }
    case 'MemberExpression':{const key=node.computed?value(node.property,scope):node.property.name;if(forbidden.has(key))throw Error('Unsafe state key');return value(node.object,scope)[key]}
    case 'AssignmentExpression':{
      if(node.operator!=='='||node.left.type!=='MemberExpression')throw Error('Unsupported state assignment');
      const key=node.left.computed?value(node.left.property,scope):node.left.property.name;if(forbidden.has(key))throw Error('Unsafe state key');
      const target=value(node.left.object,scope);return target[key]=value(node.right,scope);
    }
    case 'CallExpression':{
      if(node.callee.type!=='FunctionExpression'||node.callee.async||node.callee.generator)throw Error('Only literal-state functions are supported');
      const local=Object.create(null);const args=node.arguments.map(arg=>value(arg,scope));
      node.callee.params.forEach((p,i)=>{if(p.type!=='Identifier')throw Error('Unsupported parameter');local[p.name]=args[i]});
      for(const statement of node.callee.body.body){
        if(statement.type==='ReturnStatement')return value(statement.argument,local);
        if(statement.type==='ExpressionStatement'){value(statement.expression,local);continue}
        if(statement.type==='VariableDeclaration'){for(const decl of statement.declarations){if(decl.id.type!=='Identifier')throw Error('Unsupported variable');local[decl.id.name]=value(decl.init,local)}continue}
        throw Error('Unsupported state statement');
      }
      break;
    }
  }
  throw Error('Unsupported state syntax: '+node.type);
}
try{
  const html=fs.readFileSync(0,'utf8');if(html.length>8000000)throw Error('Page too large');
  const script=html.match(/<script[^>]*>\s*window\.__NUXT__\s*=([\s\S]*?)<\/script>/i);
  if(!script)throw Error('Nuxt state missing');
  const expression=parseExpression(script[1].trim().replace(/;\s*$/,''));
  process.stdout.write(JSON.stringify(value(expression,Object.create(null))));
}catch(error){process.stderr.write(error.message);process.exitCode=1}
