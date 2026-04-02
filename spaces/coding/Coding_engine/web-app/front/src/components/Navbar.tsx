import { Button } from "@/components/ui/button";
import { Menu, X, GithubIcon } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { EngineStatusPill } from "@/components/engine/EngineStatusPill";
import { ServiceStatusBar } from "@/components/engine/ServiceStatusBar";

const Navbar = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { label: "Projects", to: "/projects" },
    { label: "Marketplace", to: "/marketplace" },
    { label: "Docs", to: "/docs" },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-border/30">
      <div className="container mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-lg">D</span>
            </div>
            <span className="text-xl font-bold text-foreground">DaveLovable</span>
          </NavLink>

          {/* Desktop Navigation — Tab-style */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <NavLink
                key={link.label}
                to={link.to}
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </div>

          {/* Desktop CTA */}
          <div className="hidden md:flex items-center gap-3">
            <EngineStatusPill />
            <ServiceStatusBar />
            <a
              href="https://github.com/davidmonterocrespo24/DaveLovable"
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors duration-200"
            >
              <GithubIcon size={20} />
            </a>
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
            <Button variant="hero" size="sm" asChild>
              <NavLink to="/">
                Start Building
              </NavLink>
            </Button>
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden text-foreground p-2"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden pt-4 pb-6 border-t border-border/30 mt-4">
            <div className="flex flex-col gap-1">
              {navLinks.map((link) => (
                <NavLink
                  key={link.label}
                  to={link.to}
                  className={({ isActive }) =>
                    `px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                    }`
                  }
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {link.label}
                </NavLink>
              ))}
              <div className="flex flex-col gap-2 pt-4 mt-2 border-t border-border/30">
                <div className="px-4 py-1">
                  <EngineStatusPill />
                </div>
                <a
                  href="https://github.com/davidmonterocrespo24/DaveLovable"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-4 py-2 text-muted-foreground hover:text-foreground transition-colors duration-200 text-sm font-medium"
                >
                  <GithubIcon size={18} />
                  <span>GitHub</span>
                </a>
                <Button variant="ghost" size="sm">
                  Sign in
                </Button>
                <Button variant="hero" size="sm" asChild>
                  <NavLink to="/">
                    Start Building
                  </NavLink>
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
