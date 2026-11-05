"""Shopping search links carry model keywords, not unverifiable store claims."""
from urllib.parse import urlencode


def default_subcategory(product):
    category=product['category']
    name=product['name'].lower()
    if category=='手机':
        return '折叠屏手机' if any(x in name for x in ('mate x','mate xt','pura x','magic v','fold','flip','mix fold')) else '直板手机'
    if category=='电脑':
        if any(x in name for x in ('rog ally','legion go','游戏掌机')): return '游戏掌机'
        if any(x in name for x in ('mac mini','mac studio','imac','台式','desktop')): return '台式电脑'
        if any(x in name for x in ('legion','loq','rog','游戏')): return '游戏笔记本'
        if any(x in name for x in ('thinkpad','thinkbook','商务')): return '商务笔记本'
        return '轻薄笔记本'
    if category=='平板': return '小尺寸平板' if 'mini' in name else '常规平板'
    if category=='耳机':
        if any(x in name for x in ('wireless 5','颈挂')): return '颈挂式耳机'
        if any(x in name for x in ('3.5mm','type-c','经典版','有线')): return '有线耳机'
        if any(x in name for x in ('freeclip','open','开放')): return '开放式耳机'
        if any(x in name for x in ('wh-','头戴','max')): return '头戴式耳机'
        return '真无线耳机'
    if category=='相机':
        if 'osmo action' in name: return '运动相机'
        if 'osmo pocket' in name: return '口袋云台相机'
        if any(x in name for x in ('osmo 360','insta360')): return '全景相机'
        if any(x in name for x in ('x100','gr iii','卡片')): return '便携数码相机'
        if any(x in name for x in ('zv-','r50 v','r50v','vlog')): return 'Vlog相机'
        if any(x in name for x in ('r50','r100','r10','r7','z50','z30','x-s','x-t')): return 'APS-C微单'
        return '全画幅微单'
    return category


def attach_shopping(product):
    name=product['name'].replace(' 系列','').strip()
    brand=product['brand']
    aliases={'Apple':'苹果','索尼':'索尼 Sony','佳能':'佳能 Canon','尼康':'尼康 Nikon','联想':'联想 Lenovo','小米':'小米 Xiaomi'}
    prefix=aliases.get(brand,brand)
    keyword=name if brand.lower() in name.lower() else prefix+' '+name
    product['subcategory']=product.get('subcategory') or default_subcategory(product)
    product['shopping_keyword']=keyword
    product['shopping_links']=[
        {'platform':'京东','url':'https://search.jd.com/Search?'+urlencode({'keyword':keyword,'enc':'utf-8'}),'kind':'平台搜索'},
        {'platform':'淘宝','url':'https://s.taobao.com/search?'+urlencode({'q':keyword}),'kind':'平台搜索'},
        {'platform':'拼多多','url':'https://mobile.yangkeduo.com/search_result.html?'+urlencode({'search_key':keyword}),'kind':'平台搜索'},
        {'platform':'闲鱼','url':'https://www.goofish.com/search?'+urlencode({'q':keyword}),'kind':'平台搜索（含二手）'},
    ]
    return product
