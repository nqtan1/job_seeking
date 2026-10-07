/** Metropolitan and overseas France by region, with each department's main city.
 *  The value stored for a place is the department code ("75", "69", "2A"): what France Travail
 *  expects. Île-de-France comes first and Paris first within it. */
type Department = { code: string; name: string; city: string }
export type Region = { name: string; departments: Department[] }

const d = (code: string, name: string, city: string = name): Department => ({ code, name, city })

export const REGIONS: Region[] = [
  {
    name: 'Île-de-France',
    departments: [
      d('75', 'Paris'),
      d('92', 'Hauts-de-Seine', 'Nanterre'),
      d('93', 'Seine-Saint-Denis', 'Saint-Denis'),
      d('94', 'Val-de-Marne', 'Créteil'),
      d('78', 'Yvelines', 'Versailles'),
      d('91', 'Essonne', 'Évry'),
      d('95', "Val-d'Oise", 'Cergy'),
      d('77', 'Seine-et-Marne', 'Melun'),
    ],
  },
  {
    name: 'Auvergne-Rhône-Alpes',
    departments: [
      d('69', 'Rhône', 'Lyon'),
      d('38', 'Isère', 'Grenoble'),
      d('63', 'Puy-de-Dôme', 'Clermont-Ferrand'),
      d('42', 'Loire', 'Saint-Étienne'),
      d('74', 'Haute-Savoie', 'Annecy'),
      d('73', 'Savoie', 'Chambéry'),
      d('01', 'Ain', 'Bourg-en-Bresse'),
      d('26', 'Drôme', 'Valence'),
      d('07', 'Ardèche', 'Privas'),
      d('03', 'Allier', 'Moulins'),
      d('43', 'Haute-Loire', 'Le Puy-en-Velay'),
      d('15', 'Cantal', 'Aurillac'),
    ],
  },
  {
    name: 'Bourgogne-Franche-Comté',
    departments: [
      d('21', "Côte-d'Or", 'Dijon'),
      d('25', 'Doubs', 'Besançon'),
      d('71', 'Saône-et-Loire', 'Mâcon'),
      d('89', 'Yonne', 'Auxerre'),
      d('39', 'Jura', 'Lons-le-Saunier'),
      d('58', 'Nièvre', 'Nevers'),
      d('70', 'Haute-Saône', 'Vesoul'),
      d('90', 'Territoire de Belfort', 'Belfort'),
    ],
  },
  {
    name: 'Bretagne',
    departments: [
      d('35', 'Ille-et-Vilaine', 'Rennes'),
      d('29', 'Finistère', 'Brest'),
      d('56', 'Morbihan', 'Vannes'),
      d('22', "Côtes-d'Armor", 'Saint-Brieuc'),
    ],
  },
  {
    name: 'Centre-Val de Loire',
    departments: [
      d('45', 'Loiret', 'Orléans'),
      d('37', 'Indre-et-Loire', 'Tours'),
      d('28', 'Eure-et-Loir', 'Chartres'),
      d('18', 'Cher', 'Bourges'),
      d('41', 'Loir-et-Cher', 'Blois'),
      d('36', 'Indre', 'Châteauroux'),
    ],
  },
  {
    name: 'Corse',
    departments: [d('2A', 'Corse-du-Sud', 'Ajaccio'), d('2B', 'Haute-Corse', 'Bastia')],
  },
  {
    name: 'Grand Est',
    departments: [
      d('67', 'Bas-Rhin', 'Strasbourg'),
      d('68', 'Haut-Rhin', 'Colmar'),
      d('54', 'Meurthe-et-Moselle', 'Nancy'),
      d('57', 'Moselle', 'Metz'),
      d('51', 'Marne', 'Reims'),
      d('10', 'Aube', 'Troyes'),
      d('08', 'Ardennes', 'Charleville-Mézières'),
      d('52', 'Haute-Marne', 'Chaumont'),
      d('55', 'Meuse', 'Bar-le-Duc'),
      d('88', 'Vosges', 'Épinal'),
    ],
  },
  {
    name: 'Hauts-de-France',
    departments: [
      d('59', 'Nord', 'Lille'),
      d('62', 'Pas-de-Calais', 'Arras'),
      d('80', 'Somme', 'Amiens'),
      d('60', 'Oise', 'Beauvais'),
      d('02', 'Aisne', 'Laon'),
    ],
  },
  {
    name: 'Normandie',
    departments: [
      d('76', 'Seine-Maritime', 'Rouen'),
      d('14', 'Calvados', 'Caen'),
      d('50', 'Manche', 'Saint-Lô'),
      d('27', 'Eure', 'Évreux'),
      d('61', 'Orne', 'Alençon'),
    ],
  },
  {
    name: 'Nouvelle-Aquitaine',
    departments: [
      d('33', 'Gironde', 'Bordeaux'),
      d('64', 'Pyrénées-Atlantiques', 'Pau'),
      d('87', 'Haute-Vienne', 'Limoges'),
      d('86', 'Vienne', 'Poitiers'),
      d('17', 'Charente-Maritime', 'La Rochelle'),
      d('16', 'Charente', 'Angoulême'),
      d('79', 'Deux-Sèvres', 'Niort'),
      d('24', 'Dordogne', 'Périgueux'),
      d('40', 'Landes', 'Mont-de-Marsan'),
      d('47', 'Lot-et-Garonne', 'Agen'),
      d('19', 'Corrèze', 'Tulle'),
      d('23', 'Creuse', 'Guéret'),
    ],
  },
  {
    name: 'Occitanie',
    departments: [
      d('31', 'Haute-Garonne', 'Toulouse'),
      d('34', 'Hérault', 'Montpellier'),
      d('30', 'Gard', 'Nîmes'),
      d('66', 'Pyrénées-Orientales', 'Perpignan'),
      d('11', 'Aude', 'Carcassonne'),
      d('81', 'Tarn', 'Albi'),
      d('82', 'Tarn-et-Garonne', 'Montauban'),
      d('65', 'Hautes-Pyrénées', 'Tarbes'),
      d('12', 'Aveyron', 'Rodez'),
      d('32', 'Gers', 'Auch'),
      d('46', 'Lot', 'Cahors'),
      d('09', 'Ariège', 'Foix'),
      d('48', 'Lozère', 'Mende'),
    ],
  },
  {
    name: 'Pays de la Loire',
    departments: [
      d('44', 'Loire-Atlantique', 'Nantes'),
      d('49', 'Maine-et-Loire', 'Angers'),
      d('72', 'Sarthe', 'Le Mans'),
      d('85', 'Vendée', 'La Roche-sur-Yon'),
      d('53', 'Mayenne', 'Laval'),
    ],
  },
  {
    name: "Provence-Alpes-Côte d'Azur",
    departments: [
      d('13', 'Bouches-du-Rhône', 'Marseille'),
      d('06', 'Alpes-Maritimes', 'Nice'),
      d('83', 'Var', 'Toulon'),
      d('84', 'Vaucluse', 'Avignon'),
      d('05', 'Hautes-Alpes', 'Gap'),
      d('04', 'Alpes-de-Haute-Provence', 'Digne-les-Bains'),
    ],
  },
  {
    name: 'Outre-mer',
    departments: [
      d('974', 'La Réunion', 'Saint-Denis'),
      d('971', 'Guadeloupe', 'Basse-Terre'),
      d('972', 'Martinique', 'Fort-de-France'),
      d('973', 'Guyane', 'Cayenne'),
      d('976', 'Mayotte', 'Mamoudzou'),
    ],
  },
]

const BY_CODE = new Map(REGIONS.flatMap((r) => r.departments).map((x) => [x.code, x]))

/** "Paris (75)" for the capital, "Lyon · Rhône (69)" elsewhere; unknown codes are shown as typed. */
export function placeLabel(code: string): string {
  const dep = BY_CODE.get(code)
  if (!dep) return code
  return dep.city === dep.name ? `${dep.city} (${code})` : `${dep.city} · ${dep.name} (${code})`
}

/** "75,69" → "Paris (75), Lyon · Rhône (69)"; empty → "All France". */
export function placesLabel(value: string | null | undefined): string {
  const codes = (value ?? '')
    .split(/[,\s;]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean)
  return codes.length ? codes.map(placeLabel).join(', ') : 'All France'
}

const plain = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

/** Regions with only the departments matching what the user typed (city, department, region or code). */
export function filterRegions(query: string): Region[] {
  const q = plain(query.trim())
  if (!q) return REGIONS
  return REGIONS.flatMap((r) => {
    const regionHit = plain(r.name).includes(q)
    const deps = r.departments.filter(
      (x) =>
        regionHit ||
        plain(x.city).includes(q) ||
        plain(x.name).includes(q) ||
        x.code.toLowerCase() === q,
    )
    return deps.length ? [{ ...r, departments: deps }] : []
  })
}
