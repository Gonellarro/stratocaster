function openLightbox(src, text) {
    const lightbox = document.getElementById('lightbox');
    const img = document.getElementById('lightbox-img');
    const txt = document.getElementById('lightbox-txt');
    img.src = src;
    txt.textContent = text;
    lightbox.classList.add('active');
}
function closeLightbox() { document.getElementById('lightbox').classList.remove('active'); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLightbox(); });
