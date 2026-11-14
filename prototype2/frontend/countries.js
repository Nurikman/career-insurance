// ISO 3166-1 alpha-2 codes and English names. Flags are rendered from the code as emoji (regional indicators).
window.COUNTRIES = ("AF:Afghanistan|AL:Albania|DZ:Algeria|AD:Andorra|AO:Angola|AG:Antigua and Barbuda|AR:Argentina|AM:Armenia|AU:Australia|AT:Austria|" +
"AZ:Azerbaijan|BS:Bahamas|BH:Bahrain|BD:Bangladesh|BB:Barbados|BY:Belarus|BE:Belgium|BZ:Belize|BJ:Benin|BT:Bhutan|BO:Bolivia|" +
"BA:Bosnia and Herzegovina|BW:Botswana|BR:Brazil|BN:Brunei|BG:Bulgaria|BF:Burkina Faso|BI:Burundi|CV:Cabo Verde|KH:Cambodia|CM:Cameroon|" +
"CA:Canada|CF:Central African Republic|TD:Chad|CL:Chile|CN:China|CO:Colombia|KM:Comoros|CG:Congo|CD:Congo (DRC)|CR:Costa Rica|" +
"CI:Côte d'Ivoire|HR:Croatia|CU:Cuba|CY:Cyprus|CZ:Czechia|DK:Denmark|DJ:Djibouti|DM:Dominica|DO:Dominican Republic|EC:Ecuador|EG:Egypt|" +
"SV:El Salvador|GQ:Equatorial Guinea|ER:Eritrea|EE:Estonia|SZ:Eswatini|ET:Ethiopia|FJ:Fiji|FI:Finland|FR:France|GA:Gabon|GM:Gambia|" +
"GE:Georgia|DE:Germany|GH:Ghana|GR:Greece|GD:Grenada|GT:Guatemala|GN:Guinea|GW:Guinea-Bissau|GY:Guyana|HT:Haiti|HN:Honduras|HK:Hong Kong|" +
"HU:Hungary|IS:Iceland|IN:India|ID:Indonesia|IR:Iran|IQ:Iraq|IE:Ireland|IL:Israel|IT:Italy|JM:Jamaica|JP:Japan|JO:Jordan|KZ:Kazakhstan|" +
"KE:Kenya|KI:Kiribati|XK:Kosovo|KW:Kuwait|KG:Kyrgyzstan|LA:Laos|LV:Latvia|LB:Lebanon|LS:Lesotho|LR:Liberia|LY:Libya|LI:Liechtenstein|" +
"LT:Lithuania|LU:Luxembourg|MO:Macao|MG:Madagascar|MW:Malawi|MY:Malaysia|MV:Maldives|ML:Mali|MT:Malta|MH:Marshall Islands|MR:Mauritania|" +
"MU:Mauritius|MX:Mexico|FM:Micronesia|MD:Moldova|MC:Monaco|MN:Mongolia|ME:Montenegro|MA:Morocco|MZ:Mozambique|MM:Myanmar|NA:Namibia|" +
"NR:Nauru|NP:Nepal|NL:Netherlands|NZ:New Zealand|NI:Nicaragua|NE:Niger|NG:Nigeria|KP:North Korea|MK:North Macedonia|NO:Norway|OM:Oman|" +
"PK:Pakistan|PW:Palau|PS:Palestine|PA:Panama|PG:Papua New Guinea|PY:Paraguay|PE:Peru|PH:Philippines|PL:Poland|PT:Portugal|PR:Puerto Rico|" +
"QA:Qatar|RO:Romania|RU:Russia|RW:Rwanda|KN:Saint Kitts and Nevis|LC:Saint Lucia|VC:Saint Vincent and the Grenadines|WS:Samoa|" +
"SM:San Marino|ST:São Tomé and Príncipe|SA:Saudi Arabia|SN:Senegal|RS:Serbia|SC:Seychelles|SL:Sierra Leone|SG:Singapore|SK:Slovakia|" +
"SI:Slovenia|SB:Solomon Islands|SO:Somalia|ZA:South Africa|KR:South Korea|SS:South Sudan|ES:Spain|LK:Sri Lanka|SD:Sudan|SR:Suriname|" +
"SE:Sweden|CH:Switzerland|SY:Syria|TW:Taiwan|TJ:Tajikistan|TZ:Tanzania|TH:Thailand|TL:Timor-Leste|TG:Togo|TO:Tonga|TT:Trinidad and Tobago|" +
"TN:Tunisia|TR:Türkiye|TM:Turkmenistan|TV:Tuvalu|UG:Uganda|UA:Ukraine|AE:United Arab Emirates|GB:United Kingdom|US:United States|" +
"UY:Uruguay|UZ:Uzbekistan|VU:Vanuatu|VA:Vatican City|VE:Venezuela|VN:Vietnam|YE:Yemen|ZM:Zambia|ZW:Zimbabwe")
  .split("|").map(s => { const [code, name] = s.split(":"); return { code, name }; });
window.flagOf = code => code.replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0)));

// Searchable country picker: <input data-country> → dropdown with flags; value must be a country from the list.
window.countryPicker = function (input) {
  const wrap = document.createElement("div"), list = document.createElement("ul"), flag = document.createElement("span");
  wrap.className = "cpick"; list.className = "clist hide"; flag.className = "cflag";
  input.parentNode.insertBefore(wrap, input); wrap.append(flag, input, list);
  input.setAttribute("autocomplete", "off"); input.setAttribute("role", "combobox"); input.setAttribute("aria-expanded", "false");
  let items = [], active = -1;
  const norm = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const find = name => COUNTRIES.find(c => norm(c.name) === norm(name.trim()));
  const sync = () => { const c = find(input.value); flag.textContent = c ? flagOf(c.code) : "🌐"; input.setCustomValidity(c || !input.value ? "" : "Choose a country from the list"); };
  const render = () => {
    const q = norm(input.value.trim());
    items = COUNTRIES.filter(c => !q || norm(c.name).includes(q) || c.code.toLowerCase() === q)
      .sort((a, b) => (q && norm(b.name).startsWith(q)) - (q && norm(a.name).startsWith(q)));
    active = items.length ? 0 : -1;
    list.innerHTML = items.length ? items.map((c, i) => `<li data-i="${i}" class="${i === active ? "on" : ""}">${flagOf(c.code)} ${c.name}</li>`).join("") : '<li class="none">No country found</li>';
    list.classList.remove("hide"); input.setAttribute("aria-expanded", "true");
  };
  const pick = i => { if (!items[i]) return; input.value = items[i].name; close(); sync(); };
  const close = () => { list.classList.add("hide"); input.setAttribute("aria-expanded", "false"); };
  const move = d => { if (!items.length) return; active = (active + d + items.length) % items.length;
    [...list.children].forEach((li, i) => li.classList.toggle("on", i === active)); list.children[active]?.scrollIntoView({ block: "nearest" }); };
  input.addEventListener("focus", render);
  input.addEventListener("input", () => { render(); sync(); });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); list.classList.contains("hide") ? render() : move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter" && !list.classList.contains("hide")) { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", e => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); pick(+li.dataset.i); } });
  input.addEventListener("blur", () => { setTimeout(close, 100); const c = find(input.value); if (c) input.value = c.name; sync(); });
  sync();
};
