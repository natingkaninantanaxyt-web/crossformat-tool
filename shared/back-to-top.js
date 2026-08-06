// Injects a "back to top" button (see .back-to-top in theme.css) that
// appears once .page-header scrolls out of view, on every page that
// includes this script.
(function () {
    function init() {
        const btn = document.createElement('button');
        btn.className = 'back-to-top';
        btn.type = 'button';
        btn.setAttribute('aria-label', 'Back to top');
        btn.innerHTML = '<i class="fa-solid fa-arrow-up"></i>';
        document.body.appendChild(btn);

        btn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        const header = document.querySelector('.page-header');
        if (header && 'IntersectionObserver' in window) {
            const observer = new IntersectionObserver(
                ([entry]) => btn.classList.toggle('visible', !entry.isIntersecting),
                { threshold: 0 }
            );
            observer.observe(header);
        } else {
            window.addEventListener('scroll', () => {
                btn.classList.toggle('visible', window.scrollY > 300);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
