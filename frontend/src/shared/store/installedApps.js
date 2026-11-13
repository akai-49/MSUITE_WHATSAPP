// src/shared/store/installedApps.js
//
// Which MSuite apps this site has. The page sets window.msuite_apps before any module runs, so the
// menu and the routes can read it while they load.
//
// No list means show everything: the dev server has none, and neither does a tab opened before the
// deploy that added it.

export function isAppInstalled(app) {
  if (!app) return true
  const apps = typeof window !== 'undefined' ? window.msuite_apps : undefined
  return Array.isArray(apps) ? apps.includes(app) : true
}

export function only(app, items) {
  return isAppInstalled(app) ? items : []
}

// Drop entries of apps this site lacks, then any section heading left with nothing under it.
export function withoutMissingApps(entries) {
  const kept = entries.filter((entry) => isAppInstalled(entry.app))
  return kept.filter((entry, index) => {
    if (entry.type !== 'section') return true
    const next = kept[index + 1]
    return !!next && next.type !== 'section'
  })
}
