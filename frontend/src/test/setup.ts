import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView — mock it so ChatWindow's
// auto-scroll useEffect doesn't throw.
Element.prototype.scrollIntoView = vi.fn();
