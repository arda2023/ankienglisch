"""Kartenlayout für aktives Sprechen; Marker werden nur bei Anzeige ersetzt."""

FRONT_HTML = '''<div class="prompt">
  <div class="german">{{German}}</div>
  {{#Hint}}<div class="hint">Tipp: {{Hint}}</div>{{/Hint}}
</div>'''

BACK_HTML = '''{{FrontSide}}
<hr id="answer">
<div class="answer-content">
  <div class="english mk">{{English}}</div>
  {{#Trap}}<div class="trap-line mk-trap">❌ {{Trap}}</div>{{/Trap}}
  {{#Pattern}}<section><h2>🧩 Pattern</h2><div class="pattern mk">{{Pattern}}</div></section>{{/Pattern}}
  {{#Transfer1}}<section><h2>🔄 Transfer (laut aussprechen)</h2>
    <div class="transfer mk">{{Transfer1}}</div>
    {{#Transfer2}}<div class="transfer mk">{{Transfer2}}</div>{{/Transfer2}}
  </section>{{/Transfer1}}
  {{#Rule}}<blockquote>{{Rule}}</blockquote>{{/Rule}}
  {{#Alternative1}}<section class="alternatives">Auch möglich:
    <div>{{Alternative1}}</div>
    {{#Alternative2}}<div>{{Alternative2}}</div>{{/Alternative2}}
  </section>{{/Alternative1}}
</div>
<script>
(function () {
  function mark(node, className) {
    if (node.nodeType === 3) {
      var text = node.nodeValue;
      var regex = /\\[\\[([\\s\\S]+?)\\]\\]/g;
      var match, last = 0, fragment = document.createDocumentFragment();
      while ((match = regex.exec(text)) !== null) {
        fragment.appendChild(document.createTextNode(text.slice(last, match.index)));
        var span = document.createElement('span');
        span.className = className;
        span.appendChild(document.createTextNode(match[1]));
        fragment.appendChild(span);
        last = regex.lastIndex;
      }
      if (last) {
        fragment.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(fragment, node);
      }
    } else if (node.nodeType === 1) {
      if (/^(SCRIPT|STYLE)$/.test(node.tagName) ||
          /(^|\\s)(key|trap)(\\s|$)/.test(node.className)) { return; }
      var children = [], i;
      for (i = 0; i < node.childNodes.length; i++) { children.push(node.childNodes[i]); }
      for (i = 0; i < children.length; i++) { mark(children[i], className); }
    }
  }
  var nodes = document.querySelectorAll('.mk, .mk-trap');
  for (var i = 0; i < nodes.length; i++) {
    mark(nodes[i], /(^|\\s)mk-trap(\\s|$)/.test(nodes[i].className) ? 'trap' : 'key');
  }
}());
</script>'''

CSS = '''.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: 20px; line-height: 1.5; color: #252525; background: #ffffff;
  max-width: 600px; margin: 0 auto; padding: 24px 18px;
  box-sizing: border-box; overflow-wrap: break-word; text-align: left;
}
.prompt { text-align: center; }
.german { font-size: 1.35em; }
.hint, .alternatives { color: #666666; font-size: .82em; }
.hint { margin-top: 12px; }
#answer { border: 0; border-top: 1px solid #cccccc; margin: 24px 0; }
.english { font-size: 1.3em; font-weight: 700; }
.trap-line { color: #666666; margin-top: 12px; }
section { margin-top: 22px; }
h2 { font-size: .85em; font-weight: 600; margin: 0 0 8px; }
.pattern { font-family: monospace; background: #f0f0f0; padding: 12px; border-radius: 8px; }
.transfer + .transfer { margin-top: 8px; }
blockquote { border-left: 3px solid #aaaaaa; padding-left: 12px; margin: 22px 0; font-size: .9em; }
.key { color: #18733b; font-weight: 700; }
.trap { color: #b52b35; font-weight: 700; }
.nightMode.card, .night_mode.card, .nightMode .card, .night_mode .card {
  color: #eeeeee; background: #202020;
}
.nightMode .hint, .night_mode .hint, .nightMode .alternatives, .night_mode .alternatives,
.nightMode .trap-line, .night_mode .trap-line { color: #bcbcbc; }
.nightMode .pattern, .night_mode .pattern { background: #303030; }
.nightMode #answer, .night_mode #answer { border-color: #555555; }
.nightMode .key, .night_mode .key { color: #77d997; }
.nightMode .trap, .night_mode .trap { color: #ff858d; }
'''
