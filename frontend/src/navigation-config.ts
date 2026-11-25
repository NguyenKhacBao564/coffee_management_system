import { CalendarDays, ClipboardCheck, FileText, Flame, LayoutDashboard, Scale, Truck, UsersRound, type LucideIcon } from 'lucide-react'

export type MainPage = 'home' | 'drums' | 'visits' | 'scales' | 'trips' | 'schedules' | 'pending'
export type AppPage = MainPage | 'accounts' | 'pilot'

export type NavItem = {
  label: string
  icon: LucideIcon
  page: AppPage
}

export function getOperationalNav(role?: string): NavItem[] {
  if (role === 'drum_operator') {
    return [{ label: 'Trông trống cà', icon: Flame, page: 'drums' }]
  }

  if (role === 'staff') {
    return [
      { label: 'Tổng quan', icon: LayoutDashboard, page: 'home' },
      { label: 'Chuyến xe xuất / nhập', icon: Truck, page: 'visits' },
      { label: 'Tín hiệu cân', icon: Scale, page: 'scales' },
      { label: 'Chuyến xe', icon: FileText, page: 'trips' },
      { label: 'Lịch hàng', icon: CalendarDays, page: 'schedules' },
      { label: 'Cần xác nhận', icon: ClipboardCheck, page: 'pending' },
    ]
  }

  if (role === 'manager') {
    return [
      { label: 'Tổng quan', icon: LayoutDashboard, page: 'home' },
      { label: 'Trông trống cà', icon: Flame, page: 'drums' },
      { label: 'Chuyến xe xuất / nhập', icon: Truck, page: 'visits' },
      { label: 'Tín hiệu cân', icon: Scale, page: 'scales' },
      { label: 'Chuyến xe', icon: FileText, page: 'trips' },
      { label: 'Lịch hàng', icon: CalendarDays, page: 'schedules' },
      { label: 'Cần xác nhận', icon: ClipboardCheck, page: 'pending' },
    ]
  }

  if (role === 'admin') {
    // Admin does not have direct operational weighing/drum duties
    return []
  }

  return []
}

export function getAdministrationNav(role?: string): NavItem[] {
  if (role === 'admin') {
    return [{ label: 'Tài khoản & Quản trị', icon: UsersRound, page: 'accounts' }]
  }
  if (role === 'manager') {
    return [{ label: 'Quản lý nhân viên', icon: UsersRound, page: 'accounts' }]
  }
  return []
}

export function getDefaultPageForRole(role?: string): AppPage {
  if (role === 'drum_operator') return 'drums'
  if (role === 'admin') return 'accounts'
  return 'home'
}

export function isPageAllowedForRole(page: AppPage, role?: string): boolean {
  if (role === 'drum_operator') {
    return page === 'drums'
  }
  if (role === 'staff') {
    return ['home', 'visits', 'scales', 'trips', 'schedules', 'pending', 'pilot'].includes(page)
  }
  if (role === 'manager') {
    return ['home', 'drums', 'visits', 'scales', 'trips', 'schedules', 'pending', 'accounts', 'pilot'].includes(page)
  }
  if (role === 'admin') {
    return ['accounts', 'home'].includes(page)
  }
  return false
}

/** Legacy configuration for compatibility */
export const navigationConfig = {
  operational: [
    { label: 'Tổng quan', icon: LayoutDashboard, page: 'home' as const },
    { label: 'Trông trống cà', icon: Flame, page: 'drums' as const },
    { label: 'Chuyến xe xuất / nhập', icon: Truck, page: 'visits' as const },
    { label: 'Tín hiệu cân', icon: Scale, page: 'scales' as const },
    { label: 'Chuyến xe', icon: FileText, page: 'trips' as const },
    { label: 'Lịch hàng', icon: CalendarDays, page: 'schedules' as const },
    { label: 'Cần xác nhận', icon: ClipboardCheck, page: 'pending' as const },
  ],
  administration: [
    { label: 'Tài khoản', icon: UsersRound, page: 'accounts' as const },
  ],
  routes: {
    '/': 'home',
    '/drums': 'drums',
    '/visits': 'visits',
    '/pilot': 'visits',
    '/scales': 'scales',
    '/admin/accounts': 'accounts',
    '/trips': 'trips',
    '/schedules': 'schedules',
    '/pending': 'pending',
  } as Record<string, AppPage>,
  visibleOperationalPages: ['home', 'drums', 'visits', 'scales', 'trips', 'schedules', 'pending'] as MainPage[],
  showBusinessOperations: true,
} as const

export function isVisibleAppPage(page: AppPage): boolean {
  return (navigationConfig.visibleOperationalPages as readonly string[]).includes(page) || page === 'accounts' || page === 'pilot'
}
