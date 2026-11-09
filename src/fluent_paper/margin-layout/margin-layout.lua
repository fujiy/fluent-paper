-- 配置はHTMLだけの拡張とし，crossref/citeprocが扱う内容とIDは変更しない．
-- 自動生成される引用と脚注は，Quarto初期化後にJSアダプタで接続する．
function Meta(meta)
  if quarto.doc.is_format('html') then
    quarto.doc.add_html_dependency({
      name = 'mechanics-margin-layout', version = '1.0.0',
      scripts = {'margin-layout.js'}, stylesheets = {'margin-layout.css'},
    })
  end
  return meta
end

local scope_index = 0
function Div(el)
  if el.classes:includes('margin-scope') then
    -- 見出しをDivへ閉じ込めるとQuartoのTOCから落ちるため，本文を平坦化する．
    -- IDと両端だけを残し，番号・目次・相互参照は通常のAST処理へ渡す．
    scope_index = scope_index + 1
    local end_id = (el.identifier ~= '' and el.identifier or 'margin-scope') .. '-margin-end-' .. scope_index
    local start = pandoc.Div({}, el.attr)
    start.attributes['margin-end'] = end_id
    local output = pandoc.List({start})
    output:extend(el.content)
    output:insert(pandoc.Div({}, pandoc.Attr(end_id, {'margin-scope-end'})))
    return output
  end
  if not el.classes:includes('margin-item') then return nil end
  -- 明示指定されたitemはQuarto標準のcolumn-margin処理へ渡さない．
  -- JSなしとPDFでは著者のソース位置で通常表示する．
  el.classes = el.classes:filter(function(class) return class ~= 'column-margin' end)
  -- 旧配置フィルターが内側の図へ付けたmarginも，外側のitemと二重制御しない．
  return el:walk({Div = function(child)
    child.classes = child.classes:filter(function(class) return class ~= 'column-margin' end)
    return child
  end})
end

