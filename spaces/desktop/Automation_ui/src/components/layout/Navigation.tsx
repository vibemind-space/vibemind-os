import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Menu,
  X,
  ScanLine,
  Zap
} from "lucide-react";

const Navigation = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const navItems = [
    { name: "OCR Designer", path: "/", icon: <ScanLine className="w-4 h-4" /> },
    { name: "Desktop Automation", path: "/electron", icon: <Zap className="w-4 h-4" /> },
  ];

  return (
    <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-16 items-center justify-between px-6 max-w-[1600px] mx-auto">
        {/* Logo and Brand */}
        <div className="flex items-center space-x-4 cursor-pointer" onClick={() => navigate("/")}>
          <div className="bg-primary/10 p-2 rounded-lg">
            <ScanLine className="w-6 h-6 text-primary" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              OCR Desktop Automation
            </h1>
            <p className="text-xs text-muted-foreground">Live Desktop Streaming & OCR</p>
          </div>
        </div>

        {/* Desktop Navigation */}
        <div className="hidden md:flex items-center space-x-1">
          {navItems.map((item) => (
            <Button
              key={item.path}
              variant={location.pathname === item.path ? "default" : "ghost"}
              size="sm"
              onClick={() => navigate(item.path)}
              className="flex items-center space-x-2 transition-all hover:scale-105"
            >
              {item.icon}
              <span>{item.name}</span>
            </Button>
          ))}
        </div>

        {/* Mobile Menu Toggle */}
        <div className="flex items-center space-x-4">
          <Button
            variant="ghost"
            size="sm"
            className="md:hidden"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </Button>
        </div>
      </div>

      {/* Mobile Navigation */}
      {isMenuOpen && (
        <div className="md:hidden border-t bg-card/95 backdrop-blur animate-in slide-in-from-top-2">
          <div className="px-6 py-4 space-y-2">
            {navItems.map((item, index) => (
              <Button
                key={item.path}
                variant={location.pathname === item.path ? "default" : "ghost"}
                size="sm"
                onClick={() => {
                  navigate(item.path);
                  setIsMenuOpen(false);
                }}
                className="w-full justify-start flex items-center space-x-3 transition-all hover:translate-x-1"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {item.icon}
                <span>{item.name}</span>
              </Button>
            ))}
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navigation;
