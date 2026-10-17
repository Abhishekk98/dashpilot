/** Top navigation items from the design header. */
export interface NavItem {
  label: string;
  href: string;
}

export const MAIN_NAV: NavItem[] = [
  { label: "Home", href: "/" },
  { label: "Projects", href: "/projects" },
  { label: "Datasets", href: "/datasets" },
  { label: "Templates", href: "/templates" },
  { label: "Brand Kits", href: "/brand-kits" },
  { label: "Reports", href: "/reports" },
];

/** True when `href` should render as the active nav pill for `pathname`. */
export function isNavActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
