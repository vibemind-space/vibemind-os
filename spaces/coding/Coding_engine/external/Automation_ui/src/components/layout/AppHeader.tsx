import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbSeparator } from '@/components/ui/breadcrumb';
import { ArrowLeft, Home, User, Settings, HelpCircle } from 'lucide-react';
interface AppHeaderProps {
  title: string;
  subtitle?: string;
  showBackButton?: boolean;
  backPath?: string;
  actions?: React.ReactNode;
}
const AppHeader: React.FC<AppHeaderProps> = ({
  title,
  subtitle,
  showBackButton = true,
  backPath = '/dashboard',
  actions
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const getBreadcrumbs = () => {
    const pathSegments = location.pathname.split('/').filter(Boolean);
    const breadcrumbs = [{
      label: 'Dashboard',
      path: '/dashboard',
      icon: Home
    }];
    if (pathSegments.length > 0) {
      const currentPath = pathSegments[pathSegments.length - 1];
      const pathMap: Record<string, string> = {
        'workflow': 'Workflow Builder',
        'live-desktop': 'Live Desktop'
      };
      if (pathMap[currentPath]) {
        breadcrumbs.push({
          label: pathMap[currentPath],
          path: location.pathname,
          icon: undefined
        });
      }
    }
    return breadcrumbs;
  };
  const breadcrumbs = getBreadcrumbs();

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key) {
          case 'h':
            e.preventDefault();
            navigate('/dashboard');
            break;

        }
      }
      if (e.key === 'Escape' && showBackButton) {
        navigate(backPath);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate, showBackButton, backPath]);

  return (
    <header className="border-b bg-card px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          {showBackButton && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(backPath)}
              className="h-8 w-8 p-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
          )}
          
          <div>
            <Breadcrumb>
              <BreadcrumbList>
                {breadcrumbs.map((breadcrumb, index) => {
                  const IconComponent = breadcrumb.icon;
                  return (
                    <React.Fragment key={index}>
                      <BreadcrumbItem>
                        <BreadcrumbLink
                          href={breadcrumb.path}
                          onClick={(e) => {
                            e.preventDefault();
                            navigate(breadcrumb.path);
                          }}
                          className="flex items-center space-x-1"
                        >
                          {IconComponent && <IconComponent className="h-4 w-4" />}
                          <span>{breadcrumb.label}</span>
                        </BreadcrumbLink>
                      </BreadcrumbItem>
                      {index < breadcrumbs.length - 1 && <BreadcrumbSeparator />}
                    </React.Fragment>
                  );
                })}
              </BreadcrumbList>
            </Breadcrumb>
            
            <div className="mt-1">
              <h1 className="text-lg font-semibold">{title}</h1>
              {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
            </div>
          </div>
        </div>
        
        {actions && (
          <div className="flex items-center space-x-2">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
};
export default AppHeader;